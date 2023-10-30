<?php
namespace ReceiptPrintHq\EscposTools\Parser\Context;

#Includes for chillerlan/php-qrcode
use chillerlan\QRCode\{QRCode, QROptions};
use chillerlan\QRCode\Common\EccLevel;
use chillerlan\QRCode\Common\Version;
use chillerlan\QRCode\Output\QROutputInterface;
use chillerlan\QRCode\Data;

/* This class implements the internal printer state for 2D code handling. 

It is used to keep the state before printing, since the other command codes can be sent in any order before the print command.

NOTE:  the state should be cleared when the "ESC @" command (aka 'InitializeCmd') is processed.

/*  A QR code is sent over a few commands.  For reference, here is the code from python-escpos:

        def qr(
            self,
            content,
            ec=QR_ECLEVEL_L,
            size=3,
            model=QR_MODEL_2,
            native=False,
            center=False,
            impl="bitImageRaster",
        ) -> None:

            # snip, snip: I removed the qr->image conversion which is not useful

            # Native 2D code printing
            cn = b"1"  # Code type for QR code
            # Select model: 1, 2 or micro.
            self._send_2d_code_data(
                six.int2byte(65), cn, six.int2byte(48 + model) + six.int2byte(0)
            )
            # Set dot size.
            self._send_2d_code_data(six.int2byte(67), cn, six.int2byte(size))
            # Set error correction level: L, M, Q, or H
            self._send_2d_code_data(six.int2byte(69), cn, six.int2byte(48 + ec))
            # Send content & print
            self._send_2d_code_data(six.int2byte(80), cn, content.encode("utf-8"), b"0")
            self._send_2d_code_data(six.int2byte(81), cn, b"", b"0")

        def _send_2d_code_data(self, fn, cn, data, m=b"") -> None:
            """Calculate and send correct data length for`GS ( k`.

            :param fn: Function to use.
            :param cn: Output code type. Affects available data.
            :param data: Data to send.
            :param m: Modifier/variant for function. Often '0' where used.
            """
            if len(m) > 1 or len(cn) != 1 or len(fn) != 1:
                raise ValueError("cn and fn must be one byte each.")
            header = self._int_low_high(len(data) + len(m) + 2, 2)
            self._raw(GS + b"(k" + header + cn + fn + m + data)

    So we need to keep everything organized to build a QR visual.

    After that, by using chillerlan/php-qrcode, we shoud be able to make an image out of it.

*/
class Code2DStateStorage
{
    private int $qrCodeModel = 50;
    private int $qrModuleSize = 0;
    private int $qrErrorCorrectionLevel = QRCode::ECC_L;  #change type of var to ECCLevel and value to ECCLevel::L for qrcode 5.0
    private string $symbolStorage = '' ;

    public function __construct(){ $this->reset();}

    //To implement the ESC @ reset.
    public function reset(){
        $this->qrCodeModel = 50;  //50 is the default.
        $this->qrModuleSize = 4;  //TODO: The specs call for a printer default.  Denso says 4 in their guide: https://www.qrcode.com/en/howto/cell.html
        $this->qrErrorCorrectionLevel = QRCode::ECC_L; //48 (low) is the default.
        $this->symbolStorage = '';
    }

    //To implement GS ( k <Function 165>,  this sets the QR code model.  
    /*  49 Selects model 1
        50 Selects model 2
        51 Selects Micro QR Code
        This limits the data size.*/
    public function setQRModel($model){
        $x = ord($model);
        if($x === 49 || $x === 50 || $x === 51){
            $this->qrCodeModel = $x;
        }
        //TODO: We should probably return an error if another value is sent.
    }

    //To implement GS ( k <Function 167>, this sets the module size
    public function setModuleSize($n){
        $this->qrModuleSize = ord($n);
    }

    //To implement GS ( k <Function 169>, this sets the error correction level
    /*  48 Selects Error correction level L
        49 Selects Error correction level M
        50 Selects Error correction level Q
        51 Selects Error correction level H */
    public function setErrorCorrectLevel($levelByte){
        $x=ord($levelByte);
        // chillerlan/php-qrcode version          
        switch ($x) { //EccLevel::X where X is: L M Q H 
            case 48:
                $this->qrErrorCorrectionLevel = QRCode::ECC_L; #ECCLevel::L; #for qrcode 5.0
                break;
            case 49:
                $this->qrErrorCorrectionLevel = QRCode::ECC_M; #ECCLevel::M; #for qrcode 5.0
                break;
            case 50:
                $this->qrErrorCorrectionLevel = QRCode::ECC_Q; #ECCLevel::Q; #for qrcode 5.0
                break;
            case 51:
                $this->qrErrorCorrectionLevel = QRCode::ECC_H; #ECCLevel::H; #for qrcode 5.0
                break;
            default:
                //TODO: We should probably return an error if another value is sent.
                break;
            }
        
    }

    //To implement GS ( k <Function 180>, this stores the QR code data
    // The acceptable size of this data is limited by the model:  https://www.qrcode.com/en/codes/model12.html
    //  Model 1:  667 alphanumeric chars (V14 at low correction level)
    //  Model 2:  4,296 alphanumeric chars (V40 at low correction level)
    //  Micro-QR:  21 alphanumeric chars  https://www.qrcode.com/en/codes/microqr.html
    public function fillSymbolStorage($data){
        /*$maxDataBits = 0;
        switch ($this->qrCodeModel) {
            case 49:
                $maxDataBits = $this->qrErrorCorrectionLevel.getMaxBitsForVersion(new Version(14));
                break;
            case 50:
                $maxDataBits = $this->qrErrorCorrectionLevel.getMaxBitsForVersion(new Version(40));
                break;
            case 51:
                $maxDataBits = 21*8;  //TODO: check the length of a character in the standard. I assume that each char is 1 byte.
                break;
        }
        //TODO: measure the $data size, depending on it's type.   
        $dataSize = 0;  //The data size in bits.  
        //Hint: 
        QRDataModeInterface $x = new Byte($data)
        //QRCode\Data\Byte.getLengthBits()  -->> c'Est une fonction protected!!


        if ($dataSize > $maxDataBits) {
            # TODO: decide if we truncate or reject in case of overflow.


        } else {*/
            $this->symbolStorage = $data;
        //}
        
        
    }

    //To implement GS ( k <Function 182>, Transmit the size information of the symbol data in the symbol storage area
    public function printQRCodeStateInfo(){
        //TODO: implement the status info - this is probably unnecessary for the ESCPOS-netprinter project.
        //Of special interest here is the "Other information" data which states if printing is possible.
    }

    //To implement GS ( k <Function 181>, this outputs the QR code in png format as a base64 URI string
    public function getQRCodeURI(){
        // TODO: if(  $this->symbolStorage) is empty, do nothing??
        // chillerlan/PHP-QRCode version
        // this library can only output Model 2 QR codes, but we will abuse it by setting the version
        // 1) set the options
        $qroptions = new QROptions;
        $qroptions->outputType          = 'imagick';
        $qroptions->imagickFormat       = 'png32'; // e.g. png32, jpeg, webp
        $qroptions->quality = 100;
        $qroptions->outputBase64 = true;  //To make render() output the URI string directly

        //Set ecc level
        $qroptions->eccLevel = $this->qrErrorCorrectionLevel ;   

        //Set the versions from the expected model
        $qroptions->versionMin = 1;
        switch ($this->qrCodeModel) {
            case 49: 
                //49 Selects model 1
                $qroptions->versionMax = 14;
                break;
            case 50:
                # 50 Selects model 2*/
                $qroptions->versionMax = 40;
                break;
            case 51:
                # TODO:  decide what to do if someone wants a MicroQR code
                break;
            }
        // 2) generate the QR
        $qroutput = (new QRCode($qroptions))->render($this->symbolStorage);

        // 3) retourner l'URI contenant l'image PNG du code avec imagick
        return $qroutput;
        }
    
    public function getQRCodeData(){
        return $this->symbolStorage;
    }
}