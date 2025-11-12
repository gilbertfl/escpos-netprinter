<?php
namespace ReceiptPrintHq\EscposTools\Parser\Command;

use ReceiptPrintHq\EscposTools\Parser\Command\DataCmd;
use Imagick;

class SelectBitImageModeCmd extends EscposCommand implements ImageContainer
{

    private $m = null;

    private $p1 = null;

    private $p2 = null;

    private $height, $width;

    private $data = "";

    private $dataSize = null;

    public function addChar($char)
    {
        if ($this->m === null) {
            $this->m = ord($char);
            return true;
        } else if ($this->p1 === null) {
            $this->p1 = ord($char);
            return true;
        } elseif ($this->p2 === null) {
            $this->p2 = ord($char);
            $this->width = $this->p1 + $this->p2 * 256;
            if ($this->m == 32 || $this->m == 33) {
                $this->dataSize = $this->width * 3;
                $this->height = 24;
            } else {
                $this->dataSize = $this->width;
                $this->height = 8;
            }
            return true;
        } else if (strlen($this->data) < $this->dataSize) {
            $this->data .= $char;
            return true;
        }
        return false;
    }

    public function getHeight()
    {
        return $this -> height;
    }

    public function getWidth()
    {
        return $this -> width;
    }

    protected function asReflectedPbm()
    {
        // Gemerate a PBM image from the source data. If we add a PBM header to the column
        // format ESC/POS data with the width and height swapped, then we get a valid PBM, with
        // the image reflected diagonally compared with the original.
        return "P4\n" . $this -> getHeight() . " " . $this -> getWidth() . "\n" . $this -> data;
    }

    public function asPbm()
    {
        if (!class_exists(Imagick::class)) {
            return $this->asPbmUsingGD($this -> asReflectedPbm());
        }

        // Reflect image diagonally from internally generated PBM
        $pbmBlob = $this -> asReflectedPbm();
        $im = new Imagick();
        $im -> readImageBlob($pbmBlob, 'pbm');
        $im -> rotateImage('#fff', 90.0);
        $im -> flopImage();
        return $im -> getImageBlob();
    }

    public function asPng()
    {
        if (!class_exists(Imagick::class)) {
            return $this->asPngUsingGD($this -> asReflectedPbm());
        }

        // Just a format conversion PBM -> PNG
        $pbmBlob = $this -> asPbm();
        $im = new Imagick();
        $im -> readImageBlob($pbmBlob, 'pbm');
        $im->setResourceLimit(6, 1); // Prevent libgomp1 segfaults, grumble grumble.        
        $im -> setFormat('png');
        return $im -> getImageBlob();
    }

    private function asPbmUsingGD($pbmBlob)
    {
        $image = $this->createImageFromPBMUsingGd($pbmBlob);
        if (!$image) {
            throw new \Exception("No se pudo crear la imagen GD desde PBM");
        }

        $image = imagerotate($image, -90, 0);
        $width = imagesx($image);
        $height = imagesy($image);
        $flipped = imagecreatetruecolor($width, $height);
        imagecopyresampled($flipped, $image, 0, 0, $width - 1, 0, $width, $height, -$width, $height);
        imagedestroy($image);

        ob_start();
        imagegd2($flipped);
        $pngData = ob_get_clean();
        imagedestroy($flipped);

        return $pngData;
    }

    private function asPngUsingGD($pbmBlob)
    {
        $image = $this->createImageFromPBMUsingGd($pbmBlob);
        if (!$image) {
            throw new \Exception("No se pudo crear la imagen GD desde PBM");
        }

        $image = imagerotate($image, -90, 0);
        $width = imagesx($image);
        $height = imagesy($image);
        $flipped = imagecreatetruecolor($width, $height);
        imagecopyresampled($flipped, $image, 0, 0, $width - 1, 0, $width, $height, -$width, $height);
        imagedestroy($image);

        ob_start();
        imagepng($flipped);
        $pngData = ob_get_clean();
        imagedestroy($flipped);

        return $pngData;
    }

    private function createImageFromPBMUsingGd(string $pbmBlob)
    {
        $lines = preg_split('/\s+/', trim($pbmBlob));
        if (count($lines) < 3 || $lines[0] !== 'P4') {
            return null;
        }

        $width  = (int) $lines[1];
        $height = (int) $lines[2];
        $headerEnd = strpos($pbmBlob, "\n", strpos($pbmBlob, $height) + strlen($height)) + 1;
        $bitmapData = substr($pbmBlob, $headerEnd);

        $img = imagecreatetruecolor($width, $height);
        $white = imagecolorallocate($img, 255, 255, 255);
        $black = imagecolorallocate($img, 0, 0, 0);
        imagefill($img, 0, 0, $white);

        $rowBytes = (int) ceil($width / 8);
        $offset = 0;

        for ($y = 0; $y < $height; $y++) {
            $row = substr($bitmapData, $offset, $rowBytes);
            $offset += $rowBytes;

            for ($x = 0; $x < $width; $x++) {
                $byteIndex = intdiv($x, 8);
                $bitIndex = 7 - ($x % 8);
                $bit = (ord($row[$byteIndex]) >> $bitIndex) & 1;
                imagesetpixel($img, $x, $y, $bit ? $black : $white);
            }
        }

        return $img;
    }
}
