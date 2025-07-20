<?php
namespace ReceiptPrintHq\EscposTools\Parser\Context;

use Mike42\Escpos\Printer;

class InlineFormatting
{
    const JUSTIFY_LEFT = 0;
    const JUSTIFY_CENTER = 1;
    const JUSTIFY_RIGHT = 2;
    
    const FONT_A = 0;
    const FONT_B = 1;
    const FONT_C = 2;

    public $bold;
    public $widthMultiple;
    public $heightMultiple;
    public $justification;
    public $underline;
    public $invert;
    public $font;
    public $upsideDown;
    public $charCodeTable;

    public function __construct()
    {
        $this -> reset();
    }

    public function setBold($bold)
    {
        $this -> bold = $bold;
    }
    
    public function setInvert($invert)
    {
        $this -> invert = $invert;
    }

    public function setWidthMultiple($width)
    {
        $this -> widthMultiple = $width;
    }
    
    public function setHeightMultiple($height)
    {
        $this -> heightMultiple = $height;
    }

    public function setFont($font)
    {
        $this -> font = $font;
    }

    public function setJustification($justification)
    {
        $this -> justification = $justification;
    }

    public function setUnderline($underline)
    {
        $this -> underline = $underline;
    }

    public function setUpsideDown($upsideDown)
    {
        $this -> upsideDown = $upsideDown;
    }

    public static function getDefault()
    {
        return new InlineFormatting();
    }

    /**
     * This lets the client set the character encoding for the next text strings
     * 
     * This is necessary to implement ESC t and do encodings right.
     * 
     * @param $escposPageNumber A page number int (range 0-255) as defined in the ESC/POS specification
     */
    public function setCharCodeTable(int $escposPageNumber): void
    {
        switch($escposPageNumber){
            case 0:     //PC437
                $this -> charCodeTable = "CP437";
                break;
            case 1:     //Katakana
                $this -> charCodeTable = "auto"; //There does not seem to be a specific encoding in PHP, let's try the autodetect.
                break;
            case 2:     //PC850:multilingual
                $this -> charCodeTable = "CP850";
                break;
            case 3:     //PC860: Portuguese
                $this -> charCodeTable = "CP860";  
                break;
            case 4:     //4 [PC863: Canadian-French]
                $this -> charCodeTable = "CP863";  
                break;
            case 5:     //Page 5 [PC865: Nordic]
                $this -> charCodeTable = "CP865";  
                break;
            case 6:     //Page 6 [Hiragana]
                $this -> charCodeTable = "auto";  //TODO: find this one
                break;
            case 7:     //Page 7 [One-pass printing Kanji characters]
                $this -> charCodeTable = "auto";  //TODO: find this one
                break;
            case 8:     //Page 8 [One-pass printing Kanji characters]
                $this -> charCodeTable = "auto";  //TODO: find this one
                break;
            case 11:     //Page 11 [PC851: Greek]
                $this -> charCodeTable = "auto";  //TODO: find this one
                break;
            case 12:    //Page 12 [PC853: Turkish]
                $this -> charCodeTable = "auto";  //TODO: find this one
                break;
            case 13:    //Page 13 [PC857: Turkish]
                $this -> charCodeTable = "auto";  //TODO: find this one
                break;
            case 14:    //Page 14 [PC737: Greek]
                $this -> charCodeTable = "auto";  //TODO: find this one
                break;
            case 15:    //Page 15 [ISO8859-7: Greek]
                $this -> charCodeTable = "ISO-8859-7";  
                break;
            case 16:    //Page 16 [WPC1252]
                $this -> charCodeTable = "CP1252";
                break;
            case 17:    //Page 17 [PC866: Cyrillic #2]
                $this -> charCodeTable = "CP866";  
                break;
            case 18:    //Page 18 [PC852: Latin 2]
                $this -> charCodeTable = "auto";  //TODO: find this one
                break;
            case 19:    //Page 19 [PC858: Euro]
                $this -> charCodeTable = "auto";  //TODO: find this one
                break;
            case 20:    //Page 20 [Thai Character Code 42]
                $this -> charCodeTable = "auto";  //TODO: find this one
                break;
            case 21:    //Page 21 [Thai Character Code 11]
                $this -> charCodeTable = "auto";  //TODO: find this one
                break;
            case 22:    //Page 22 [Thai Character Code 13]
                $this -> charCodeTable = "auto";  //TODO: find this one
                break;
            case 23:    //Page 23 [Thai Character Code 14]
                $this -> charCodeTable = "auto";  //TODO: find this one
                break;
            case 24:    //Page 24 [Thai Character Code 16]
                $this -> charCodeTable = "auto";  //TODO: find this one
                break;
            case 25:    //Page 25 [Thai Character Code 17]
                $this -> charCodeTable = "auto";  //TODO: find this one
                break;
            case 26:    //Page 26 [Thai Character Code 18]
                $this -> charCodeTable = "auto";  //TODO: find this one
                break;
            case 30:    //Page 30 [TCVN-3: Vietnamese]
                $this -> charCodeTable = "auto";  //TODO: find this one
                break;
            case 31:    //Page 31 [TCVN-3: Vietnamese]
                $this -> charCodeTable = "auto";  //TODO: find this one
                break;
            case 32:    //Page 32 [PC720: Arabic]
                $this -> charCodeTable = "auto";  //TODO: find this one
                break;
            case 33:    //Page 33 [WPC775: Baltic Rim]
                $this -> charCodeTable = "auto";  //TODO: find this one
                break;
            case 34:    //Page 34 [PC855: Cyrillic]
                $this -> charCodeTable = "auto";  //TODO: find this one
                break;
            case 35:    //Page 35 [PC861: Icelandic]
                $this -> charCodeTable = "auto";  //TODO: find this one
                break;
            case 36:    //Page 36 [PC862: Hebrew]
                $this -> charCodeTable = "CP862";  
                break;
            case 37:    //Page 37 [PC864: Arabic]
                $this -> charCodeTable = "CP864";  
                break;
            case 38:    //Page 38 [PC869: Greek]
                $this -> charCodeTable = "CP869";  
                break;
            case 39:    //Page 39 [ISO8859-2: Latin 2]
                $this -> charCodeTable = "ISO-8859-2";
                break;
            case 40:    //Page 40 [ISO8859-15: Latin 9]
                $this -> charCodeTable = "auto";    //TODO: find this one
                break;
            case 41:    //Page 41 [PC1098: Farsi]
                $this -> charCodeTable = "auto";  //TODO: find this one
                break;
            case 42:    //Page 42 [PC1118: Lithuanian]
                $this -> charCodeTable = "auto";  //TODO: find this one
                break;
            case 43:    //Page 43 [PC1119: Lithuanian]
                $this -> charCodeTable = "auto";  //TODO: find this one
                break;
            case 44:    //Page 44 [PC1125: Ukrainian]
                $this -> charCodeTable = "auto";  //TODO: find this one
                break;
            case 45:    //Page 45 [WPC1250: Latin 2]
                $this -> charCodeTable = "auto";  //TODO: find this one
                break;
            case 46:    //Page 46 [WPC1251: Cyrillic]
                $this -> charCodeTable = "CP1251";  
                break;
            case 47:    //Page 47 [WPC1253: Greek]
                $this -> charCodeTable = "WINDOWS-1253";  
                break;
            case 48:    //Page 48 [WPC1254: Turkish]
                $this -> charCodeTable = "WINDOWS-1254";  
                break;
            case 49:    //Page 49 [WPC1255: Hebrew]
                $this -> charCodeTable = "WINDOWS-1255";  
                break;
            case 50:    //Page 50 [WPC1256: Arabic]
                $this -> charCodeTable = "WINDOWS-1256";  
                break;
            case 51:    //Page 51 [WPC1257: Baltic Rim]
                $this -> charCodeTable = "WINDOWS-1257";  
                break;
            case 52:    //Page 52 [WPC1258: Vietnamese]
                $this -> charCodeTable = "CP1258";  
                break;
            case 53:    //Page 53 [KZ-1048: Kazakhstan]
                $this -> charCodeTable = "auto";  //TODO: find this one
                break;
            case 66:    //Page 66 [Devanagari]
                $this -> charCodeTable = "auto";  //TODO: find this one
                break;
            case 67:    //Page 67 [Bengali]
                $this -> charCodeTable = "auto";  //TODO: find this one
                break;
            case 68:    //Page 68 [Tamil]
                $this -> charCodeTable = "auto";  //TODO: find this one
                break;
            case 69:    //Page 69 [Telugu]
                $this -> charCodeTable = "auto";  //TODO: find this one
                break;
            case 70:    //Page 70 [Assamese]
                $this -> charCodeTable = "auto";  //TODO: find this one
                break;
            case 71:    //Page 71 [Oriya]
                $this -> charCodeTable = "auto";  //TODO: find this one
                break;
            case 72:    //Page 72 [Kannada]
                $this -> charCodeTable = "auto";  //TODO: find this one
                break;
            case 73:    //Page 73 [Malayalam]
                $this -> charCodeTable = "auto";  //TODO: find this one
                break;
            case 74:    //Page 74 [Gujarati]
                $this -> charCodeTable = "auto";  //TODO: find this one
                break;
            case 75:    //Page 75 [Punjabi]
                $this -> charCodeTable = "auto";  //TODO: find this one
                break;
            case 82:    //Page 82 [Marathi]
                $this -> charCodeTable = "auto";  //TODO: find this one
                break;
            default:
                //Invalid code received, or pages 254 and 255 -> we ignore the command as described in the ESC/POS spec.
                break;
        }
    }
    public function reset()
    {
        $this -> bold = false;
        $this -> widthMultiple = 1;
        $this -> heightMultiple = 1;
        $this -> justification = InlineFormatting::JUSTIFY_LEFT;
        $this -> underline = 0;
        $this -> invert = false;
        $this -> font = 0;
        $this -> upsideDown = false;
        $this -> charCodeTable = "CP437";  //Set page 0 as default
    }
}
