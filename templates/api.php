<?php

print_r($_POST);
die;

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    http_response_code(405);
    echo "Method Not Allowed";
    exit;
}

$orderId = $_POST['order_id'] ?? null;
$content = $_POST['file'] ?? null;

if (!$orderId || !$content) {
    http_response_code(400);
    echo "Missing order_id or file";
    exit;
}

$tmpDir = __DIR__ . '/../tmp';
$receiptDir = __DIR__ . '/receipts';
$csvPath = __DIR__ . '/receipt_list.csv';

@mkdir($tmpDir, 0777, true);
@mkdir($receiptDir, 0777, true);
@touch($csvPath);

$filename = "sales-order-receipt-$orderId.escpos";
$htmlFile = "order-$orderId.html";
$tmpPath = "$tmpDir/$filename";
$htmlPath = "$receiptDir/$htmlFile";

// Save file
file_put_contents($tmpPath, $content);

// Clean up old file
@unlink($htmlPath);
file_put_contents($csvPath, preg_replace("/^$orderId,.*\$/m", '', file_get_contents($csvPath)));

// Convert to HTML
$html = shell_exec("php /home/escpos-emu/esc2html.php $tmpPath");
file_put_contents($htmlPath, $html);

// Register
file_put_contents($csvPath, "$orderId,$htmlFile\n", FILE_APPEND);

echo json_encode([
    'success' => true,
    'url' => "http://localhost:8087/recus/$orderId"
]);
