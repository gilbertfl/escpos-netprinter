<?php
namespace ReceiptPrintHq\EscposTools\Parser\Command;

use ReceiptPrintHq\EscposTools\Parser\Command\DataCmd;

// This interprets the "GS ( k" commands. 
// Official Description: Performs data processing related to 2-dimensional codes 
//                       (PDF417, QR Code, MaxiCode, 2-dimensional GS1 DataBar, Composite Symbology). 
class Code2DDataCmd extends DataCmd
{
    private $pL = null;
    private $pH = null;
    private $cn = null;
  
    //Process one command byte.  Return true if the byte is interpreted without error
    /*This symbol has the following format: GS ( k pL pH cn fn [parameters]
        Symbol type is specified by cn
        Function code fn specifies the function
        pL and pH specify the number of bytes following cn as (pL + pH × 256)
        The [parameters] are described in each function. 
    (ref: Epson ESC/POS Command Reference for TM Printers)
    */
    public function addChar($char)
    {
        //Lets begin by getting the size from the first 4 bytes
        if ($this -> pL === null){
            $this -> pL = ord($char);
            return true;
        }
        elseif ($this -> pH === null){
            $this -> pH = ord($char);
            //Calculate the length of fn+[parameters] - the spec starts counting AFTER cn
            $this -> dataSize = $this -> pL + $this -> pH * 256;
            return true;
        }
        //Now interpret the subcommand
        elseif ($this -> cn === null) {
            $this -> cn = ord($char);

            //If the command is known, assign subCommand with the interpreter class
            if($this->cn == 48){
                //this is a PDF417 code command
            }
            elseif($this->cn == 49){
                //this is a QR code command
                $this->subCommand = new QRcodeSubCommand($this->datasize);
            }
            elseif(50 <= $this->cn <= 54) {
                //this is one of the other valid codes
            }
            else return false; //This code is not a valid function. Stop all processing.
            return true;
        }
        else  { //Process everything after cn
            if ($this -> subCommand === null){
                //If subCommand is null, the command is not implemented. Stop all processing.
                return false;
            }
            else {
                //Send the fn and parameter data to the subcommand
                return $this -> subCommand -> addChar($char);
            }
        }
    }
}
