import pymysql
import httpx
from config import Config
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_db_connection():
    """Create a new database connection (used only when PHP bridge is disabled)."""
    try:
        connection = pymysql.connect(
            host=Config.MYSQL_HOST,
            port=Config.MYSQL_PORT,
            user=Config.MYSQL_USER,
            password=Config.MYSQL_PASSWORD,
            database=Config.MYSQL_DATABASE,
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )
        print("Database connected!!")
        return connection
    except Exception as e:
        logger.error(f"Error connecting to database: {e}")
        raise

def execute_query_via_php_bridge(query, params=None):
    """
    Execute query via PHP bridge on OVH server.
    This allows access to OVH MySQL which doesn't allow remote connections.
    """
    try:
        # Format query with parameters if provided
        if params:
            # Convert parameterized query to formatted query for PHP bridge
            # Replace %s with actual values (properly escaped)
            if isinstance(params, (list, tuple)):
                formatted_params = []
                for param in params:
                    if isinstance(param, str):
                        # Escape single quotes for SQL
                        formatted_params.append(f"'{param.replace(chr(39), chr(39)+chr(39))}'")
                    elif param is None:
                        formatted_params.append('NULL')
                    else:
                        formatted_params.append(str(param))

                # Replace %s placeholders with formatted values
                for param in formatted_params:
                    query = query.replace('%s', param, 1)

        logger.info(f"Executing query via PHP bridge: {query[:200]}...")

        # Send POST request to PHP bridge
        response = httpx.post(
            Config.PHP_BRIDGE_URL,
            data={"query": query},
            timeout=30.0
        )
        response.raise_for_status()

        result = response.json()

        # PHP bridge returns {"data": [...]} for SELECT queries
        # or might return error
        if "error" in result:
            logger.error(f"PHP bridge returned error: {result['error']}")
            return {"error": result["error"]}

        # Check if this is an UPDATE/INSERT/DELETE query (non-SELECT)
        query_type = query.strip().upper().split()[0]
        is_modification_query = query_type in ['UPDATE', 'INSERT', 'DELETE']

        # Handle response format: {"status": "success", "data": [...]}
        # or just {"data": [...]}
        if "status" in result and result["status"] == "success":
            if is_modification_query:
                # For UPDATE/INSERT/DELETE, return success with affected rows if available
                logger.info(f"PHP bridge {query_type} query successful")
                return {"affected_rows": result.get("affected_rows", result.get("rows_affected", 0)), "success": True}
            else:
                # For SELECT queries
                logger.info(f"PHP bridge query successful, returned {len(result.get('data', []))} rows")
                return {"data": result.get("data", [])}
        elif "data" in result:
            logger.info(f"PHP bridge query successful, returned {len(result.get('data', []))} rows")
            return result
        else:
            # If no error and no data, assume success for modification queries
            if is_modification_query:
                logger.info(f"PHP bridge {query_type} query completed")
                return {"affected_rows": result.get("affected_rows", result.get("rows_affected", 0)), "success": True}
            logger.error(f"Unexpected PHP bridge response format: {result}")
            return {"error": "Unexpected response format from PHP bridge"}

    except httpx.HTTPError as e:
        logger.error(f"HTTP error connecting to PHP bridge: {e}")
        return {"error": f"PHP bridge connection failed: {str(e)}"}
    except Exception as e:
        logger.error(f"Error executing query via PHP bridge: {e}")
        logger.error(f"Query: {query}")
        return {"error": str(e)}

def execute_query_direct(query, params=None):
    """Execute a query directly via MySQL connection (Railway fallback)."""
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(query, params)
            if query.strip().upper().startswith('SELECT'):
                result = cursor.fetchall()
                return {"data": result}
            else:
                connection.commit()
                return {"affected_rows": cursor.rowcount}
    except Exception as e:
        logger.error(f"Database query failed: {e}")
        logger.error(f"Query: {query}")
        logger.error(f"Params: {params}")
        return {"error": str(e)}
    finally:
        connection.close()

def execute_query(query, params=None):
    """
    Execute a database query using either PHP bridge or direct connection.
    The method is controlled by Config.USE_PHP_BRIDGE.
    """
    if Config.USE_PHP_BRIDGE:
        logger.info("Using PHP bridge for database query")
        return execute_query_via_php_bridge(query, params)
    else:
        logger.info("Using direct MySQL connection for database query")
        return execute_query_direct(query, params)
        
def get_all_table_names():
    """
    Fetches a list of all table names in the currently connected database.
    """
    query = "SHOW TABLES" 
    result = execute_query(query)
    if "error" in result:
        return result
        
    table_names = []
    if result.get("data"):
        if result["data"]:
            column_name = list(result["data"][0].keys())[0]
            table_names = [row[column_name] for row in result["data"]]
    
    return {"data": table_names}
