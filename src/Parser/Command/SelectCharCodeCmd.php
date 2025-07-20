<?php
namespace ReceiptPrintHq\EscposTools\Parser\Command;

use ReceiptPrintHq\EscposTools\Parser\Command\CommandOneArg;

/**
 * This class implements the ESC t command
 */
class SelectCharCodeCmd extends CommandOneArg
{
    public function getCodePage():int {
        return parent::getArg();
    }
}
