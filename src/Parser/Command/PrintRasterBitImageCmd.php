<?php
namespace ReceiptPrintHq\EscposTools\Parser\Command;

use ReceiptPrintHq\EscposTools\Parser\Command\EscposCommand;
use Imagick;

class PrintRasterBitImageCmd extends EscposCommand implements ImageContainer
{
    private $m = null;
    private $xL = null;
    private $xH = null;
    private $yL = null;
    private $yH = null;
    private $width = null;
    private $height = null;
    private $dataLen = null;
    private $data = "";

    public function addChar($char)
    {
        if ($this -> dataLen !== null) {
            if (strlen($this -> data) < $this -> dataLen) {
                $this -> data .= $char;
                return true;
            }
            return false;
        }
        if ($this -> m === null) {
            $this -> m = ord($char);
            return true;
        }
        if ($this -> xL === null) {
            $this -> xL = ord($char);
            return true;
        }
        if ($this -> xH === null) {
            $this -> xH = ord($char);
            return true;
        }
        if ($this -> yL === null) {
            $this -> yL = ord($char);
            return true;
        }
        if ($this -> yH === null) {
            $this -> yH = ord($char);
            $this -> width = $this -> xL + $this -> xH * 256;
            $this -> height = $this -> yL + $this -> yH * 256;
            $this -> dataLen = $this -> width * $this -> height;
            return true;
        }
        return false;
    }
    public function getHeight()
    {
        return $this -> height;
    }

    public function asPbm()
    {
        return "P4\n" . $this -> getWidth() . " " . $this -> getHeight() . "\n" . $this -> data;
    }

    public function getWidth()
    {
        return $this -> width * 8;
    }

    public function asPng()
    {
        // Just a format conversion PBM -> PNG
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
