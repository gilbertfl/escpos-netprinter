<?php
namespace ReceiptPrintHq\EscposTools\Parser\Command;

use ReceiptPrintHq\EscposTools\Parser\Context\InlineFormatting;

interface TextContainer
{
    public function getText(InlineFormatting $context);
}
