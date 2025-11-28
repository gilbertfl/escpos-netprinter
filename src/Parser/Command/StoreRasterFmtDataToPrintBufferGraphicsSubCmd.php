<?php
namespace ReceiptPrintHq\EscposTools\Parser\Command;

use ReceiptPrintHq\EscposTools\Parser\Command\Command;
use ReceiptPrintHq\EscposTools\Parser\Command\DataSubCmd;
use \Imagick;

class StoreRasterFmtDataToPrintBufferGraphicsSubCmd extends DataSubCmd implements ImageContainer
{
    private $tone = null;
    private $color = null;
    
    private $widthMultiple = null;
    private $heightMultiple = null;
    
    private $x1 = null;
    private $x2 = null;
    private $y1 = null;
    private $y2 = null;
    
    public function __construct($dataSize)
    {
        $this -> dataSize = $dataSize - 8;
    }

    public function addChar($char)
    {
        if ($this -> tone == null) {
            $this -> tone = ord($char);
            return true;
        } else if ($this -> color === null) {
            $this -> color = ord($char);
            return true;
        } else if ($this -> widthMultiple === null) {
            $this -> widthMultiple = ord($char);
            return true;
        } else if ($this -> heightMultiple === null) {
            $this -> heightMultiple = ord($char);
            return true;
        } else if ($this -> x1 === null) {
            $this -> x1 = ord($char);
            return true;
        } else if ($this -> x2 === null) {
            $this -> x2 = ord($char);
            return true;
        } else if ($this -> y1 === null) {
            $this -> y1 = ord($char);
            return true;
        } else if ($this -> y2 === null) {
            $this -> y2 = ord($char);
            return true;
        } else if (strlen($this -> data) < $this -> dataSize) {
            $this -> data .= $char;
            return true;
        }
        return false;
    }

    public function getWidth()
    {
        return $this -> x1 + $this -> x2 * 256;
    }
    
    public function getHeight()
    {
        return $this -> y1 + $this -> y2 * 256;
    }
    
    public function asPbm()
    {
        return "P4\n" . $this -> getWidth() . " " . $this -> getHeight() . "\n" . $this -> data;
    }
    
    public function asPng()
    {
        $pbmBlob = $this -> asPbm();
        if (!class_exists(Imagick::class)) {
            return $this->asPngUsingGD($pbmBlob);
        }

        $im = new Imagick();
        $im -> readImageBlob($pbmBlob, 'pbm');
        $im->setResourceLimit(6, 1); // Prevent libgomp1 segfaults, grumble grumble.
        $im -> setFormat('png');
        return $im -> getImageBlob();
    }

    private function asPngUsingGD($pbmBlob) {
        $fp = fopen("php://memory", "r+");
        fwrite($fp, $pbmBlob);
        rewind($fp);

        $header = trim(fgets($fp));
        do {
            $pos = ftell($fp);
            $line = trim(fgets($fp));
        } while ($line !== false && str_starts_with($line, "#"));
        fseek($fp, $pos);

        [$width, $height] = array_map("intval", preg_split('/\s+/', trim(fgets($fp))));
        $img = imagecreatetruecolor($width, $height);
        imagefilledrectangle($img, 0, 0, $width, $height, imagecolorallocate($img, 255, 255, 255));

        $black = imagecolorallocate($img, 0, 0, 0);
        $rowBytes = (int)ceil($width / 8);
        for ($y = 0; $y < $height; $y++) {
            $row = fread($fp, $rowBytes);
            $bits = unpack("C*", $row);
            $x = 0;
            foreach ($bits as $byte) {
                for ($bit = 7; $bit >= 0; $bit--) {
                    if ($x >= $width) break;
                    $val = ($byte >> $bit) & 1;
                    if ($val === 1) {
                        imagesetpixel($img, $x, $y, $black);
                    }
                    $x++;
                }
            }
        }

        fclose($fp);
        ob_start();
        imagepng($img);
        imagedestroy($img);
        return ob_get_clean();
    }
}
