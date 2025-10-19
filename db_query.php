<?php
/**
 * PHP Bridge for MySQL Database Access
 * This file allows the Flask backend to execute SQL queries on OVH MySQL
 * which only accepts localhost connections.
 */

// Set headers for JSON response and CORS
header('Content-Type: application/json');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: POST, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type');

// Handle preflight OPTIONS request
if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    http_response_code(200);
    exit();
}

// Only allow POST requests
if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    http_response_code(405);
    echo json_encode(['error' => 'Method not allowed. Use POST.']);
    exit();
}

// Database configuration for OVH
// IMPORTANT: Update these with your actual OVH MySQL credentials
$host = 'medfeluuser.mysql.db';  // OVH MySQL hostname (usually yourusername.mysql.db)
$dbname = 'medfeluuser';          // Database name
$username = 'medfeluuser';        // MySQL username
$password = 'Medfeluuser123';     // MySQL password

try {
    // Create MySQLi connection
    $mysqli = new mysqli($host, $username, $password, $dbname);

    // Check connection
    if ($mysqli->connect_error) {
        throw new Exception('Connection failed: ' . $mysqli->connect_error);
    }

    // Set charset to utf8mb4
    $mysqli->set_charset('utf8mb4');

    // Get the SQL query from POST data
    $query = $_POST['query'] ?? '';

    if (empty($query)) {
        echo json_encode(['error' => 'No query provided']);
        exit();
    }

    // Execute the query
    $result = $mysqli->query($query);

    if ($result === false) {
        throw new Exception('Query failed: ' . $mysqli->error);
    }

    // Check if it's a SELECT query or modifying query
    $queryType = strtoupper(substr(trim($query), 0, 6));

    if ($queryType === 'SELECT' || $queryType === 'SHOW' || $queryType === 'DESCRI') {
        // Fetch all results for SELECT queries
        $rows = [];
        while ($row = $result->fetch_assoc()) {
            $rows[] = $row;
        }
        echo json_encode(['data' => $rows]);
        $result->free();
    } else {
        // For INSERT, UPDATE, DELETE queries
        $affectedRows = $mysqli->affected_rows;
        echo json_encode([
            'data' => [],
            'affected_rows' => $affectedRows
        ]);
    }

    $mysqli->close();

} catch (Exception $e) {
    // Return error as JSON
    http_response_code(500);
    echo json_encode(['error' => $e->getMessage()]);
}
?>
