<?php
namespace ReceiptPrintHq\EscposTools\Parser\Command;

use ReceiptPrintHq\EscposTools\Parser\Command\Code2DSubCommand;


class QRcodeSubCommand extends Code2DSubCommand
{

    private $fn = null;

    public function __construct($dataSize)
    {
        $this->dataSize = $dataSize - 1;  //$dataSize is the size of [parameters], so we exclude the fn byte
    }

    public function addChar($char)
    {
        if ($this->fn === null){
            //First extract the QR function
            $this -> fn = ord($char);
            return true;
        }
        else{ 
            //then send [parameters] into $data
            return parent::addChar($char);
        }
    }

    public function get_fn(){
        return $this->fn;
    }

    public function isAvailableAs($interface){
        return parent::isAvailableAs($interface);
    }
}