<?php
namespace ReceiptPrintHq\EscposTools\Parser\Command;

use ReceiptPrintHq\EscposTools\Parser\Command\DataSubCmd;
use ReceiptPrintHq\EscposTools\Parser\Command\Command;


class QRcodeSubCommand extends DataSubCmd
{

    private $fn = null;
    private $data = "";
    private int $dataSize;


    public function __construct($newdataSize)
    {
        $this->dataSize = $newdataSize;  //$dataSize is the size of [parameters], so we exclude the fn byte
    }

    public function addChar($char)
    {
        if ($this->fn === null){
            //First extract the QR function
            $this -> fn = ord($char);
            return true;
        }
        elseif(strlen($this -> data) < $this -> dataSize) {  
                //then send [parameters] into $data
                //Copied from DataSubCmd.
                $this -> data .= $char;
                return true;
            }
        else{
                return false;
            }
    }

    public function get_fn(){
        return $this->fn;
    }

    public function get_data(){
        return $this->data;
    }

	/**
	 * @return int
	 */
	public function getDataSize(): int {
		return $this->dataSize;
	}
}