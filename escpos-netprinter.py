import os
from flask import Flask, redirect, render_template, request, session, url_for
from os import getenv
from io import BufferedWriter
import csv
import subprocess
from subprocess import CompletedProcess
from pathlib import PurePath
from lxml import html, etree
from datetime import datetime
from zoneinfo import ZoneInfo
from flask_babel import Babel
import babel_config

import threading 
import socketserver

#Network ESC/pos printer server
class ESCPOSServer(socketserver.TCPServer):

    def handle_timeout(self) -> None:
        print ('Print service timeout!', flush=True)
        return super().handle_timeout()



#Network ESC/pos printer request handling
class ESCPOSHandler(socketserver.StreamRequestHandler):
    
    """
        Voir l'APG Epson section "Processing the Data Received from the Printer"
    """
    timeout = 10  #On abandonne une réception après 10 secondes - un compromis pour assurer que tout passe sans se bourrer de connections zombies.
    netprinter_debugmode = "false"
    
    # Receive the print data and dump it in a file.
    def handle(self):
        print (f"Address connected: {self.client_address}", flush=True)
        self.netprinter_debugmode = getenv('ESCPOS_DEBUG', "false")
        bin_filename = PurePath('web', 'tmp', "reception.bin")
        with open(bin_filename, "wb") as binfile:

            #Read everything until we get EOF, and keep everything in a receive buffer
            receive_buffer:bytes = b''

            try:
                # Implement the "Real-time command processing" block described in the Epson APG.
                # How:  Skim the received data byte by byte to respond to status checks as they come.   
                # We are making this as simple as possible so we do not slow down the print:  
                #   1)  watch for ESC/POS commands that could lead to a status request               
                #   2)  If this byte is none of those, send it forward without further processing
                #   3)  If this byte is a candidate command:
                #       a) Check a second byte for a status request
                #       b) if the second byte does not indicate a status request, send the two bytes forward without further processing
                #       c) if the second byte indicates a status request, reply appropriately then send all processed data bytes forward
                
                while (indata_statuscheck := self.rfile.read(1)):
                    match indata_statuscheck:
                        case  b'\x1D' :  # GS
                            #This is potentially a status request.
                            indata_statuscheck = indata_statuscheck + self.rfile.read(1) #Get the second command byte

                            match indata_statuscheck:
                                case b'\x1D\x72':
                                    #Respond to GS r status requests
                                    gs_r_data:bytes = self.respond_gs_r()
                                    indata_statuscheck = indata_statuscheck + gs_r_data
                                    if self.netprinter_debugmode == True:
                                        print(f"GS r received containing {len(indata_statuscheck)} bytes", flush=True)

                                case b'\x1D\x49':
                                    # Respond to GS I printer ID request
                                    gs_i_data:bytes = self.respond_gs_i()
                                    indata_statuscheck = indata_statuscheck + gs_i_data
                                    if self.netprinter_debugmode == True:
                                        print(f"GS i received containing {len(indata_statuscheck)} bytes", flush=True)

                                case b'\x1D\x67':
                                    # Respond to GS g maintenance counter requests
                                    gs_g2_data:bytes = self.respond_gs_g()
                                    indata_statuscheck = indata_statuscheck + gs_g2_data
                                    if self.netprinter_debugmode == True:
                                        print(f"GS g received containing {len(indata_statuscheck)} bytes", flush=True)
                                
                                case b'\x1D\x28':
                                    # Respond to GS ( E and GS ( H requests
                                    gs_parens_data:bytes = self.respond_gs_parens()
                                    indata_statuscheck = indata_statuscheck + gs_parens_data
                                    if self.netprinter_debugmode == True:
                                        print(f"GS ( received containing {len(indata_statuscheck)} bytes", flush=True)

                                case b'\x1D\x6A':
                                    # Respond to GS j request ASB for ink
                                    gs_j_data:bytes = self.respond_gs_j()
                                            
                                    indata_statuscheck = indata_statuscheck + gs_j_data
                                    if self.netprinter_debugmode == True:
                                        print(f"GS j received containing {len(indata_statuscheck)} bytes", flush=True)

                                case b'\x1D\x3A' | b'\x1D\x63':
                                    #Requests with zero argument bytes
                                    pass
                                
                                case b'\x1D\x21' | b'\x1D\x42' | b'\x1D\x62'| b'\x1D\x2F' | b'\x1D\x48' | b'\x1D\x54' | b'\x1D\x56' | b'\x1D\x62' | b'\x1D\x66' | b'\x1D\x68' | b'\x1D\x6A' | b'\x1D\x77':
                                    #Requests with one argument byte
                                    # NOTE: the GS V command has 1 or 2 arguments, but the second cannot be mistaken for a command so we wait next loop to read it in.
                                    #Munch on it and pass it on
                                    indata_statuscheck = indata_statuscheck + self.rfile.read(1)
                                    
                                case b'\x1D\x4C' | b'\x1D\x50' | b'\x1D\x57' | b'\x1D\x5C' :
                                    #Requests with two argument bytes
                                    #Munch on em and pass it on
                                    indata_statuscheck = indata_statuscheck + self.rfile.read(2)
                                    
                                case b'\x1D\x7A' | b'\x1D\x5E' :
                                    #Requests with three argument bytes
                                    #Munch on em and pass it on
                                    indata_statuscheck = indata_statuscheck + self.rfile.read(3)
                                    
                                case b'\x1D\x43' :
                                    # GS C: obsolete commands
                                    #Munch on it and pass it on
                                    next_byte:bytes = self.rfile.read(1)
                                    match next_byte:
                                        case b'\x30':
                                            # GS C 0 - counter print mode
                                            next_byte = next_byte + self.rfile.read(2)
                                            
                                        case b'\x31':
                                            # GS C 1 Select count mode
                                            next_byte = next_byte + self.rfile.read(6)
                                            
                                        case b'\x32':
                                            # GS C 2
                                            next_byte = next_byte + self.rfile.read(2)
                                            
                                        case b'\x3B':
                                            # GS C ; - 5 bytes with separators
                                            next_byte = next_byte + self.rfile.read(10)
                                    
                                    indata_statuscheck = indata_statuscheck + next_byte
                                
                                case b'\x1D\x61':
                                    # GS a - request enable automatic status back
                                    n:bytes =  self.rfile.read(1)
                                    indata_statuscheck = indata_statuscheck + n
                                    # We send the ASB once, in case the client checks for it.
                                    if n==b'\x00':
                                        pass  #The request is disable ASB -> we send nothing back.
                                    else:
                                        self.send_basic_ASB_OK() 
                                
                                case b'\x1D\x44':
                                    # GS D has 2 functions.
                                    m:bytes = self.rfile.read(1)
                                    fn:bytes = self.rfile.read(1)
                                    indata_statuscheck = indata_statuscheck + m + fn
                                    match fn:
                                        case b'\x43':
                                            # <fn=63> Define Windows BMP NV graphics data
                                            # read the bytes before the BMP
                                            indata_statuscheck = indata_statuscheck + self.rfile.read(5)
                                            
                                            #We are at the start of the BMP here.
                                            indata_statuscheck = indata_statuscheck + self.consume_bmp_file()
                                            
                                            if self.netprinter_debugmode == True:
                                                print(f"GS D <fn=63> BMP NV graphics data received: {indata_statuscheck}", flush=True)
                                            
                                        case b'\x53':
                                            # <fn=83> Define Windows BMP download graphics data
                                            # read the bytes before the BMP
                                            indata_statuscheck = indata_statuscheck + self.rfile.read(5)
                                            
                                            #We are at the start of the BMP here.
                                            indata_statuscheck = indata_statuscheck + self.consume_bmp_file()
                                            
                                            if self.netprinter_debugmode == True:
                                                print(f"GS D <fn=83> BMP download data received: {indata_statuscheck}", flush=True)
                                            
                                        case _:
                                            if self.netprinter_debugmode == True:
                                                print(f"Unknown GS D command received : {indata_statuscheck}", flush=True)
                                                
                                    if self.netprinter_debugmode == True:
                                        print(f"GS D command received containing {len(indata_statuscheck)} bytes", flush=True)
                                
                                case b'\x1D\x6B':
                                    # GS k - print barcode request
                                    
                                    # Find out the function
                                    m:bytes = self.rfile.read(1)
                                    
                                    # Read the barcode data.   There are 2 functions with different formats, depending on m
                                    barcode_data:bytes = b''
                                    match m:
                                        case b'\x00':
                                            # Function A - the data is null-terminated.
                                            # Read one byte at a time until \x00 comes
                                            while True:
                                                chunk:bytes = self.rfile.read(1)
                                                if not chunk: 
                                                    break
                                                barcode_data = barcode_data + chunk
                                                if b'\x00' in chunk: 
                                                    break

                                        case b'\x65':
                                            # Function B - the data length is specified
                                            n:bytes = self.rfile.read(1)
                                            barcode_data = n + self.rfile.read(int.from_bytes(n)) 
                                    
                                    # Now send all that data forward
                                    indata_statuscheck = indata_statuscheck + m + barcode_data
                                    
                                    if self.netprinter_debugmode == True:
                                        print(f"GS k received containing {len(indata_statuscheck)} bytes", flush=True)

                                
                                case b'\x1D\x51':
                                    # GS Q 0 - print bit image
                                    m:bytes = self.rfile.read(2) # the 0 plus the m
                                    xL:bytes = self.rfile.read(1)
                                    xH:bytes = self.rfile.read(1)
                                    yL:bytes = self.rfile.read(1)
                                    yH:bytes = self.rfile.read(1)
                                    # Read the image then send it forward
                                    indata_statuscheck = indata_statuscheck + m + xL + xH + yL + yH + self.consume_byte_array(xL, xH, yL, yH)
                                    if self.netprinter_debugmode == True:
                                        print(f"GS Q 0 received containing {len(indata_statuscheck)} bytes", flush=True)
                                
                                case b'\x1D\x2A':
                                    # GS * define downloaded image
                                    x:bytes = self.rfile.read(1)
                                    y:bytes = self.rfile.read(1)
                                    
                                    indata_statuscheck = indata_statuscheck + self.rfile.read(int.from_bytes(x) * int.from_bytes(y) * 8)
                                    if self.netprinter_debugmode == True:
                                        print(f"GS * received containing {len(indata_statuscheck)} bytes", flush=True)
                                    
                                
                                case _:
                                    #This is not a status request
                                    if self.netprinter_debugmode == True:
                                        print(f"Almost-status bytes: {indata_statuscheck}", flush=True)
                        
                        case b'\x10' :  # DLE 
                            #This is potentially a status request.
                            indata_statuscheck = indata_statuscheck + self.rfile.read(1) #Get the second command byte

                            match indata_statuscheck:
                                case b'\x10\x04':
                                    # Respond to DLE EOT status requests
                                    dle_eot_data:bytes = self.respond_dle_eot()
                                    indata_statuscheck = indata_statuscheck + dle_eot_data #append the DLE EOT bytes to the processed bytes
                                    if self.netprinter_debugmode == True:
                                        print(f"DLE EOT received containing {len(indata_statuscheck)} bytes", flush=True)

                                case b'\x10\x14':
                                    # Respond to DLE DC4 
                                    dle_dc4_data: bytes = self.respond_dle_dc4()
                                    indata_statuscheck = indata_statuscheck + dle_dc4_data
                                    if self.netprinter_debugmode == True:
                                        print(f"DLE EOT received containing {len(indata_statuscheck)} bytes", flush=True)

                                case _:
                                    #This is not a status request
                                    if self.netprinter_debugmode == True:
                                        print(f"Almost-status bytes: {indata_statuscheck}", flush=True)

                        case b'\x1B' :  # ESC
                            #This is potentially a status request.
                            indata_statuscheck = indata_statuscheck + self.rfile.read(1) #Get the second command byte

                            match indata_statuscheck:
                                case b'\x1B\x76':
                                    # Respond to ESC v request
                                    self.wfile.write(b'\x00')  #Respond roll paper present and adequate
                                    self.wfile.flush()
                                    if self.netprinter_debugmode == True:
                                        print(f"ESC v received containing {len(indata_statuscheck)} bytes", flush=True)
                                
                                case b'\x1B\x75':
                                    #Respond to ESC u request
                                    #Read the n byte
                                    n:bytes = self.rfile.read(1)
                                    self.wfile.write(b'\x00')  #Respond drawer kick-out LOW
                                    self.wfile.flush()
                                    indata_statuscheck = indata_statuscheck + n
                                    if self.netprinter_debugmode == True:
                                        print(f"ESC u received containing {len(indata_statuscheck)} bytes", flush=True)
                                        
                                case _:
                                    # All other ESC commands have one n byte
                                    indata_statuscheck = indata_statuscheck + self.rfile.read(1)
                                    if self.netprinter_debugmode == True:
                                        print(f"Non-blocking ESC command received: {indata_statuscheck}", flush=True)
                        
                        case b'\x1C':  #FS
                            indata_statuscheck = indata_statuscheck + self.rfile.read(1) #Get the second command byte
                            match indata_statuscheck:
                                case b'\x1C\x28':
                                    #This an FS ( request
                                    fs_parens_data:bytes = self.respond_fs_parens()
                                    indata_statuscheck = indata_statuscheck + fs_parens_data
                                    if self.netprinter_debugmode == True:
                                        print(f"FS ( received containing {len(indata_statuscheck)} bytes", flush=True)

                                case b'\x1C\x26' | b'\x1C\x2E':
                                    #Subrequests with zero argument bytes
                                    pass
                                
                                case b'\x1C\x21' | b'\x1C\x2D' | b'\x1C\x43'| b'\x1C\x57':
                                    #Subrequests with one argument byte
                                    #Munch on it and pass it on
                                    indata_statuscheck = indata_statuscheck + self.rfile.read(1)
                                
                                case b'\x1C\x3F' | b'\x1C\x53' | b'\x1C\x70':
                                    #Subrequests with 2 argument bytes
                                    #Munch on em and pass it on
                                    indata_statuscheck = indata_statuscheck + self.rfile.read(2)

                                case b'\x1C\x32':
                                    #FS 2 command has c1 c2 then k bits (arbitrarily decided by the printer.   We'll munch 32  as in the APG)
                                    indata_statuscheck = indata_statuscheck + self.rfile.read(4)  # Munch 4 bytes (32 bits)

                                case b'\x1C\x67':
                                    # FS g
                                    
                                    next_byte:bytes = self.rfile.read(1)
                                    match next_byte:
                                        case b'\x31':
                                            # FS g 1 - write to NV memory
                                            # FS g 1 has m then 4 a bytes then nl, ng then (nL + nH × 256) data bytes
                                            next_byte = next_byte + self.rfile.read(5) #munch on unused bytes: m a1 a2 a3 a4
                                            # then read pL and pH
                                            nL:bytes = self.rfile.read(1)
                                            nH:bytes = self.rfile.read(1)
                                            
                                            #send all that data forward
                                            next_byte = next_byte + nL + nH + self.consume_parameter_data(nL, nH)
                                            
                                        case b'\x32':
                                            # FS g 2 - read from NV user memory
                                            # FS g 2 has m then 4 a bytes then nl, ng.  Must send back "header to NUL"
                                            next_byte = next_byte + self.rfile.read(5) #munch on unused bytes: m a1 a2 a3 a4
                                            # Get the expected number of bytes to send
                                            nL:bytes = self.rfile.read(1)
                                            nH:bytes = self.rfile.read(1)
                                            nb_bytes = int.from_bytes(nL)  + (int.from_bytes(nH) * 256)
                                            self.wfile.write(b'\x5f') #Send the header
                                            self.wfile.write(b'\x0F' * nb_bytes) #Send the expected amount of "data"
                                            self.wfile.write(b'\x00') #Send NULL
                                            self.wfile.flush()
                                            #send all the received data forward
                                            next_byte = next_byte + nL + nH
                                            
                                    indata_statuscheck = indata_statuscheck + next_byte
                                    if self.netprinter_debugmode == True:
                                        print(f"FS g received containing {len(indata_statuscheck)} bytes", flush=True)

                                case b'\x1C\x71':
                                    # FS q - store non-volatile raster graphics.
                                    # get n - the number if images to munch on
                                    n:bytes = self.rfile.read(1)
                                    indata_statuscheck = indata_statuscheck + n
                                    
                                    for i in range(int.from_bytes(n)):
                                        # munch on one image and pass it on
                                        xL = self.rfile.read(1)
                                        xH = self.rfile.read(1)
                                        yL = self.rfile.read(1)
                                        yH = self.rfile.read(1)
                                        
                                        indata_statuscheck = indata_statuscheck + self.consume_byte_array(xL, xH, yL, yH)
                                        
                                    if self.netprinter_debugmode == True:
                                        print(f"FS q received containing {len(indata_statuscheck)} bytes", flush=True)
                                        

                                case _:
                                    if self.netprinter_debugmode == 'True':
                                        print(f"Unknown FS request received: {indata_statuscheck}", flush=True)
                        case _:
                            #This byte is uninteresting data for this block's purposes, no processing necessary.
                            pass

                    #Append the processed byte(s) to the receive buffer
                    receive_buffer = receive_buffer + indata_statuscheck

        
            except TimeoutError:
                print("Timeout while reading")
                self.connection.close()
                if len(receive_buffer) > 0:
                    print(f"{len(receive_buffer)} bytes received.")
                    if self.netprinter_debugmode == 'True':
                        print("-----start of data-----\n", flush=True)
                        print(receive_buffer, flush=True)
                        print("\n-----end of data-----", flush=True)
                else: 
                    print("No data received!", flush=True)
            
            except Exception as err:
                print(f"Unexpected {err=}, {type(err)=}")
                raise    
                    
            else:
                #Quand on a reçu le signal de fin de transmission
                print(f"{len(receive_buffer)} bytes received.", flush=True)

                if self.netprinter_debugmode == 'True':
                    print("-----start of data-----\n", flush=True)
                    print(receive_buffer, flush=True)
                    print("\n-----end of data-----", flush=True)

                #Écrire les données reçues dans le fichier.
                if len(receive_buffer) > 0:
                    binfile.write(receive_buffer)
                    binfile.close()  #Écrire le fichier et le fermer
                    #traiter le fichier reception.bin pour en faire un HTML
                    self.print_toHTML(binfile, bin_filename)
                elif self.netprinter_debugmode == 'True':
                        print("No data received: nothing will be printed.", flush=True)

        #The binfile should auto-close here.

        self.wfile.write(b"ESCPOS-netprinter: All done!")  #A enlever plus tard?  On dit au client qu'on a fini.
        self.wfile.flush()
        self.connection.close()

        print ("Data reception finished, signature sent.", flush=True)

    def consume_bmp_file(self) -> bytes:
        """ Consume a BMP file for the GS D command

        Returns:
            bytes: The complete BMP file
        """      
          
        bmp_file:bytes = b''

        # BMP header has the size in byte
        # The first 2 bytes are supposed to be "BM" (\x42\x4D)        
        header_field:bytes = self.rfile.read(2)
        bmp_file = bmp_file + header_field
        if header_field == b'\x42\x4D': 
            #Confirmed BMP.  Get the size (4 bytes)
            bmp_size:bytes = self.rfile.read(4)
            bmp_data:bytes = b''
            if int.from_bytes(bmp_size) == 0:
                print("Error:  zero-byte-long argument specified", flush=True)
            else:
                bmp_data =  self.rfile.read(int.from_bytes(bmp_size)) # Send these bytes forward in all cases
            bmp_file = bmp_file + bmp_size + bmp_data
        else:
            if self.netprinter_debugmode == True:
                print(f"GS D received non-BMP file - did not read the data", flush=True)
        return bmp_file

    def respond_gs_j(self) -> bytes:
        #Consume a GS j request and respond to the client if necessary
        gs_j_data:bytes = self.rfile.read(1)
                                    
        match gs_j_data:
            case b'\x00':
                # request to stop ASB - we do nothing
                pass
            case _:
                #Now we send the 4-byte ASB all-clear for ink
                self.wfile.write(b'\x35\x40\x40\x00')
        return gs_j_data

    def respond_dle_dc4(self) -> bytes:
        #Consume a DLE DC4 request and respond to functions 1, 2, 3, 7 and 8
        if self.netprinter_debugmode == 'True': 
            print("DLE DC4 request", flush=True)
        next_in:bytes = self.rfile.read(1)  #Get the first byte
        match next_in:
            case b'\x07':
                m:bytes = self.rfile.read(1)
                match m:
                    case b'\x01':
                        #Transmit the 4 bytes of the all-clear ASB status like GS a
                        self.send_basic_ASB_OK() 
                    
                    case b'\x02':
                        #Transmit the 4 bytes of the all-clear extended ASB status like FS ( e 
                        self.send_extended_ASB_OK()
                    
                    case b'\x04':
                        #Transmit the offline response like GS ( H <f=49>
                        self.wfile.write(b'\x37\x23\x00') #Send the empty Offline response to the client
                        
                    case b'\x05':
                        #Transmit battery status - printer dependent so we send anything
                        self.wfile.write(b'\x01')

                    case _:
                        if self.netprinter_debugmode == 'True':
                            print(f"Unknown DLE DC4 <fn=7> request received: {next_in}", flush=True)

                next_in = next_in + m

            case b'\x01':
                #Generate pulse - no need to respond, so we munch on the 2 extra bytes
                next_in = next_in + self.rfile.read(2)

            case b'\x02':
                #Power-off sequence
                #Munch on the 2 extra fixed bytes
                next_in = next_in + self.rfile.read(2)
                #send the power-off notice
                self.wfile.write(b'\x3B\x30\x00') 
                #Here a physical printer would stop everything, but we will go on.
            
            case b'\x03':
                #Sound buzzer - no need to respond, so we munch on the 4 extra bytes.
                next_in = next_in + self.rfile.read(4)
            
            case b'\x08':
                #Clear buffer(s)
                #Munch on the 7 extra fixed bytes
                next_in = next_in + self.rfile.read(7)
                #Send the Buffer Clear response
                self.wfile.write(b'\x37\x25\x00') 
            
            case _:
                #This request is about something else, nothing to do.
                if self.netprinter_debugmode == 'True':
                    print(f"Unknown DLE DC4 request received: {next_in}", flush=True)
                    
        return next_in

    def respond_fs_parens(self) -> bytes:
        #Consume and process one FS ( request
        if self.netprinter_debugmode == 'True': 
            print("FS ( request", flush=True)
            
        next_in:bytes = self.rfile.read1(1)  #Get the command's next byte
        
        match next_in:
            case b'\x65':  # e
                # FS ( e Enable/disable Automatic Status Back (ASB) for optional functions (extended status)
                
                if self.netprinter_debugmode == 'True': 
                    print("FS ( e request", flush=True)
                
                #  First, get the next bytes
                pL:bytes = self.rfile.read(1) # Get pL byte 
                pH:bytes = self.rfile.read(1) # Get pH byte
                m:bytes = self.rfile.read(1) # Get m byte
                n:bytes = self.rfile.read(1) # Get n byte
                next_in = next_in + pL + pH + m + n # Send these bytes forward in all cases

                match n:
                    case b'\x00':
                        #Request to disable ASB:  nothing to return
                        pass
                    case _:
                        #Enabling any status (specifying n != 0) starts extended ASB
                        self.send_extended_ASB_OK() 

            case b'\x45':  # FS ( E receipt enhancement control
                
                if self.netprinter_debugmode == 'True': 
                    print(f"FS ( E request", flush=True)
                
                #  First, get the size and fn bytes
                pL:bytes = self.rfile.read(1) # Get pL byte 
                pH:bytes = self.rfile.read(1) # Get pH byte
                fn:bytes = self.rfile.read(1) # Get fn byte
                
                match fn:
                    case b'\x3d': #fn 61 needs a response
                        m:bytes = self.rfile.read(1)
                        c:bytes = self.rfile.read(1)
                        
                        next_in = next_in + pL + pH + fn + m + c
                        
                        match c:
                            case b'\x30':  #48
                                # Send back top logo info:  m kc1 kc2 a n
                                self.wfile.write(b'\x02\x32\x32\x49\x04')
                                self.wfile.flush()
                                if self.netprinter_debugmode == 'True':
                                    print("FS ( E <fn=61> top logo codes sent", flush=True) 
                                    
                            case b'\x31':  #49
                                # Send back bottom logo info:  m kc1 kc2 a 
                                self.wfile.write(b'\x02\x32\x32\x49')
                                self.wfile.flush()
                                if self.netprinter_debugmode == 'True':
                                    print("FS ( E <fn=61> bottom logo codes sent", flush=True) 
                                    
                            case b'\x32':  #50
                                # Send back extended top/bottom logo info:  m [a1 n1] [a2 n2] ... [ak nk]
                                # if nk = 48 the setting is disabled;  let's do that.
                                # NOTE: the spec fixes m = 2.  The specification does not specify how to tell the value of k, but there a 5 possible pairs.  Let's do 2 pairs.
                                self.wfile.write(b'\x02'+ b'\x40\x30' + b'\x41\x30')
                                self.wfile.flush()
                                if self.netprinter_debugmode == 'True':
                                    print("FS ( E <fn=61> extended top/bottom logo codes sent", flush=True) 
                                    
                            case _:
                                if self.netprinter_debugmode == 'True':
                                    print(f"Unknown FS ( E <fn=61> request received: {next_in}", flush=True) 
                       
                    case _:
                        #In other cases, no response needed
                        next_in = next_in + pL + pH + fn + self.consume_parameter_data(pL, pH) # Send these bytes forward in all cases
                        
                        if fn in [b'\x3c', b'\x3e', b'\x3f', b'\x40', b'\x41', b'\x43']:
                            if self.netprinter_debugmode == 'True': 
                                print(f"No-response-needed FS ( E <fn={fn}> request", flush=True)
                        else:
                            if self.netprinter_debugmode == 'True':
                                print(f"Unknown FS ( E request received: {next_in}", flush=True) 
            
            case  b'\x4C': # FS ( L Select label and black mark control function(s)
                
                if self.netprinter_debugmode == 'True': 
                    print(f"FS ( L request", flush=True)
                
                #  First, get the size and fn bytes
                pL:bytes = self.rfile.read(1) # Get pL byte 
                pH:bytes = self.rfile.read(1) # Get pH byte
                fn:bytes = self.rfile.read(1) # Get fn byte   
                
                match fn:
                    case b'\x22': #fn=34 needs a response
                        # FS ( L <fn=34> Paper layout information transmission
                        n:bytes = self.rfile.read(1)
                        next_in = next_in + n
                        le_n:bytes = str.encode(f'{int.from_bytes(n)}') #Convert n as text
                        
                        match n:
                            case b'\x40':
                                # n=64 Paper layout setting value (in mm)
                                #Send the response Header to null with each value expressed as text
                                self.wfile.write(b'\x37\x4b') 
                                self.wfile.write(le_n)  
                                self.wfile.write(b'\x1f')
                                self.wfile.write(b'0\x1f')  #sm=0 This is a Receipt (no black mark)
                                self.wfile.write(b'0\x1f')  #sa=0 Does not specify the distance from the print reference to the next print reference 
                                self.wfile.write(b'\x1f'*4) #sb, sc, sd, se are omitted, not pertinent for sm=0
                                self.wfile.write(b'800')  #The receipt width is 80mm (the unit is 0.1mm)
                                self.wfile.write(b'\x00')
                                self.wfile.flush()  #Send the response back.
                                if self.netprinter_debugmode == 'True': 
                                    print(f"FS ( L <fn=34> <n=64> Paper layout settings sent", flush=True)
                                
                            
                            case b'\x50':
                                #n=80 Paper layout effective value  (in dots)
                                #Send the response Header to null with each value expressed as text
                                self.wfile.write(b'\x37\x4b') 
                                self.wfile.write(le_n)  
                                self.wfile.write(b'\x1f')
                                self.wfile.write(b'0\x1f')  #sm=0 This is a Receipt (no black mark)
                                self.wfile.write(b'0\x1f')  #sa=0 Does not specify the distance from the print reference to the next print reference 
                                self.wfile.write(b'\x1f'*4) #sb, sc, sd, se are omitted, not pertinent for sm=0
                                self.wfile.write(b'512')  #The receipt width is 80mm (the unit is dots, we choose 512 dots @ 180 DPI like the EPSON TM-88V)
                                self.wfile.write(b'\x00')
                                self.wfile.flush()  #Send the response back.     
                                
                                if self.netprinter_debugmode == 'True': 
                                    print(f"FS ( L <fn=34> <n=80> Paper layout settings sent", flush=True)                           
                            
                            case _:
                                #Unknown n, we send nothing back.
                                if self.netprinter_debugmode == 'True': 
                                    print(f"Unknown FS ( L <fn=34> <n={le_n}> Paper layout request received", flush=True)
                    
                    case b'\x30':  #fn=48 needs a response
                        # FS ( L <fn=48> Transmit the positioning information
                        # The paper layout is "No reference (do not use layout)"
                        m:bytes = self.rfile.read(1)
                        next_in = next_in + m
                        
                        #Send the response Header to null
                        self.wfile.write(b'\x37\x38')
                        self.wfile.write(b'\x40') #Information a:  Bits 0,1,2 are 0 and bit 6 is fixed at 1.
                        self.wfile.write(b'\x43') #Information b: Bits 0 and 1 are 1 and bit 6 is fixed at 1.
                        self.wfile.write(b'\x00')
                        self.wfile.flush()  #Send the response back. 
                        
                        if self.netprinter_debugmode == 'True': 
                            print(f"FS ( L <fn=48>  Paper positioning info sent", flush=True)   
                    
                    
                    case b'\x21' | b'\x41' | b'\x42' | b'\x43' | b'\x43': #fn=33, 65, 66, 67, 80
                        #No response needed
                        #WARNING:  the documentation says that <function 80> is hex 43, but it should be 50.  I'll follow the documentation.
                        next_in = next_in + self.consume_parameter_data(pL, pH) # Send these bytes forward
                        
                        if self.netprinter_debugmode == 'True': 
                            print(f"No-response-needed FS ( E <fn={fn}> request", flush=True)
                            
                    case _:  
                        next_in = next_in + self.consume_parameter_data(pL, pH) # Send these bytes forward
                        
                        if self.netprinter_debugmode == 'True':
                                print(f"Unknown FS ( E request received: {next_in}", flush=True) 
                    
                            
            case _:
                if self.netprinter_debugmode == 'True':
                    print(f"Unknown FS ( request received: {next_in}", flush=True)

        return next_in

    def send_basic_ASB_OK(self) -> None:
        """Transmit the 4 bytes of the all-clear ASB status
        """        
        self.wfile.write(b'\x00\x00\x00\x00')
        self.wfile.flush()
        if self.netprinter_debugmode == 'True':
            print("4-byte ASB status sent", flush=True)

    def send_extended_ASB_OK(self) -> None:
        """Return all-clear extended ASB status 
        """        
        self.wfile.write(b'\x39\x00\x40\x00')  
        self.wfile.flush()
        if self.netprinter_debugmode == 'True':
            print("4-byte extended ASB status sent", flush=True)

    def respond_gs_g(self) -> bytes:
        """ Consume a GS G request and respond to <fn=2> if necessary

        Returns:
            bytes: the consumed request
        """        
        if self.netprinter_debugmode == 'True': 
            print("GS g request", flush=True)
        next_in:bytes = self.rfile.read(2)  #Get the 2 and m bytes
        match next_in:
            case b'\x32\x00': 
                #Respond to GS g 2 with a constant number
                #TODO: someday implement counters in case some client checks their progress
                next_in = next_in + self.rfile.read(2)  #Get 2 more bytes (nL and nH)
                self.wfile.write(b'\x5F\x01\x00') #Send one(1) for all counters
                self.wfile.flush()
                if self.netprinter_debugmode == 'True':
                    print("4-byte extended ASB status sent", flush=True) 

            case b'\x30\x00':
                # Read in the 2 other bytes and send them on
                next_in = next_in + self.rfile.read(2)  #Get 2 more bytes (nL and nH)
                
            case _:
                if self.netprinter_debugmode == 'True':
                    print(f"Non-status GS g request received: {next_in}", flush=True)

        return next_in

    def respond_gs_i(self) -> bytes:
        """Consume and process one GS i request and respond to the client if necessary

        Returns:
            bytes: The consumed request
        """        

        #First, define inner helper functions
        def send_gs_i_printer_info_A(contents:bytes) -> None:
            #Helper to respond with Printer Info A
            self.wfile.write(b'\x3D') #Header
            self.wfile.write(contents[:80])  # Max 80 bytes here, so send only that slice
            self.wfile.write(b'\x00') #NUL
            self.wfile.flush()
    
        def send_gs_i_printer_info_B(contents:bytes) -> None:
            #Helper to respond with Printer Info B
            self.wfile.write(b'\x5F') #Header
            self.wfile.write(contents[:80])  # Max 80 bytes here, so send only that slice
            self.wfile.write(b'\x00') #NUL
            self.wfile.flush()

        # Let's do this
        if self.netprinter_debugmode == 'True': 
            print("GS i request", flush=True)
        next_in:bytes = self.rfile.read1(1)  #The n is at most 1 byte
        match next_in:
            case b'\x01' | b'\x31':  #1 or 49
                #Transmit some printer model ID byte
                self.wfile.write(b'\x01') #TODO: choose a model ID
                self.wfile.flush()
                if self.netprinter_debugmode == 'True':
                    print("Printer model ID byte sent", flush=True)   
            
            case b'\x02' | b'\x32': # 2 or 50
                #Transmit Printer type ID
                self.wfile.write(b'\x02') # No multi-byte chars, autocutter installed, no DM-D
                self.wfile.flush()
                if self.netprinter_debugmode == 'True':
                    print("Printer type ID byte sent", flush=True)   

            case b'\x03' | b'\x33': # 3 or 51
                #Transmit some version ID byte
                self.wfile.write(b'\x23') #TODO: put the version ID somewhere central to facilitate releases
                self.wfile.flush()
                if self.netprinter_debugmode == 'True':
                    print("Printer version ID byte sent", flush=True)   

            case b'\x21':  # 33
                #Transmit printer type information - supported functions
                # We send a 3-byte all-clear response
                first_byte = b'\x02' # No multi-byte chars, autocutter installed, no DM-D
                second_byte = b'\x40' #Fixed
                third_byte = b'\x40'  #No peeler.
                send_gs_i_printer_info_A(first_byte + second_byte + third_byte)
                if self.netprinter_debugmode == 'True':
                    print("Printer supported functions sent", flush=True)                 

            case b'\x41': # 65
                #Transmit printer firmware version
                send_gs_i_printer_info_B(b'release 2.3')  #TODO: put the version number somewhere central to facilitate releases
                if self.netprinter_debugmode == 'True':
                    print("Printer firmware version sent", flush=True) 

            case b'\x42' | b'\x43':  # 66 or 67
                #Transmit maker name or model name - could be different but not important.
                send_gs_i_printer_info_B(b'ESCPOS-netprinter')
                if self.netprinter_debugmode == 'True':
                    print("Printer maker or model name sent", flush=True) 
          
            case b'\x44': # 68
                #Transmit printer serial number
                send_gs_i_printer_info_B(b'netprinter_1') #TODO: create a serial number for each instance (??)
                if self.netprinter_debugmode == 'True':
                    print("Printer serial sent", flush=True) 

            case b'\x45': # 69
                #Transmit printer font of language
                send_gs_i_printer_info_B(b'PC850 Multilingual')
                if self.netprinter_debugmode == 'True':
                    print("Printer language sent", flush=True) 
                    
            case b'\x23' | b'\x24' | b'\x60' | b'\x6E' :
                #These are model-specific requests for Printer information A
                send_gs_i_printer_info_A(b'\x01\x01\x01') # We can send anything, but the client will wait for Printer Information A before continuing.
                if self.netprinter_debugmode == 'True':
                    print("Model-specific Printer Info A sent", flush=True)   
                    
            case b'\x6F' :
                #These are model-specific requests for Printer Information B
                send_gs_i_printer_info_B(b'Netprinter')
                if self.netprinter_debugmode == 'True':
                    print("Model-specific Printer Info B sent", flush=True)  
                    
            case b'\x70':
                #These are model-specific requests for Printer Information B
                send_gs_i_printer_info_B(b'Netprinter')
                if self.netprinter_debugmode == 'True':
                    print("Model-specific Printer Info B sent", flush=True)
                
            case _:
                if self.netprinter_debugmode == 'True':
                    print(f"Unknown GS i request received: {next_in}", flush=True)

        return next_in

    def respond_gs_r(self) -> bytes:
        """Consume one GS r request and respond to the client

        Returns:
            bytes: the consumed request
        """        
        if self.netprinter_debugmode == 'True': 
            print("GS r request", flush=True)
            
        request:bytes = self.rfile.read1(1)  #The n is at most 1 byte
        match request:
            case b'\x01':  #n=1
                #Send paper status adequate and present
                self.wfile.write(b'\x00')
                self.wfile.flush()
                if self.netprinter_debugmode == 'True':
                    print("Paper status sent", flush=True) 
            case b'\x31':  #n=49
                #Send paper status adequate and present (alternate)
                self.wfile.write(b'\x00')
                self.wfile.flush()
                if self.netprinter_debugmode == 'True':
                    print("Paper status sent", flush=True) 
            case b'\x02':  #n=2
                #Send drawer kick-out connector status
                self.wfile.write(b'\x00')
                self.wfile.flush()
                if self.netprinter_debugmode == 'True':
                    print("Drawer kick-out status sent", flush=True) 
            case b'\x32':  #n=50
                #Send drawer kick-out connector status (alternate)
                self.wfile.write(b'\x00')
                self.wfile.flush()
                if self.netprinter_debugmode == 'True':
                    print("Drawer kick-out status sent", flush=True) 
            case b'\x04':  #n=4
                #Send ink status adequate
                self.wfile.write(b'\x00')
                self.wfile.flush()
                if self.netprinter_debugmode == 'True':
                    print("Ink status sent", flush=True) 
            case b'\x34':  #n=52
                #Send ink status adequate
                self.wfile.write(b'\x00')
                self.wfile.flush()
                if self.netprinter_debugmode == 'True':
                    print("Ink status sent", flush=True)
            case _:
                if self.netprinter_debugmode == 'True':
                    print(f"Unknown GS r request received: {request}", flush=True)
        return request
    
    def respond_gs_parens(self) -> bytes:
        """ Consume and respond to one GS ( request

        Returns:
            bytes: the consumed request
        """        

        request:bytes = self.rfile.read(1) #Start by getting the next byte
        match request:
            case b'\x45': #E
                #Set user setup command
                request = request + self.process_gs_parens_E()
               
            case b'\x48': #H
                #Transmission + response or status (not for OPOS or Java POS, and very mysterious and printer-dependant)
                request = request + self.process_gs_parens_H()

            case _:
                if self.netprinter_debugmode == 'True':
                    print(f"Non-status GS ( request received: {request}", flush=True)
        
        return request

    def process_gs_parens_E(self) -> bytes:
        pL:bytes = self.rfile.read(1) # Get pL byte 
        pH:bytes = self.rfile.read(1) # Get pH byte
        fn:bytes = self.rfile.read(1) # Get fn byte
        request:bytes = pL + pH + fn # Send these bytes forward in all cases
       
        match fn:
            case b'\x01':
                        # Respond to user setting mode start request
                request = request + self.rfile.read(2) #read d1 and d2
                self.wfile.write(b'\x37\x20\x00')  # Respond OK
                self.wfile.flush()
                if self.netprinter_debugmode == 'True':
                    print("Mode change notice sent", flush=True)

            case b'\x04':
                        # Respond with settings of the memory switches
                a:bytes = self.rfile.read(1)  #read a
                request = request + a
                match a:
                    case b'\x01':
                                # Respond with: Power-on notice disabled, Receive buffer large, busy when buffer full, 
                                #               receive error ignored, auto line-feed disabled, DM-D not connected,
                                #               RS-232 pins 6 and 25 not used.
                        response:bytes = b'\x30\x30\x31\x31\x30\x30\x30\x30'
                        self.wfile.write(b'\x37\x21' + response + b'\x00') 
                        self.wfile.flush()
                        if self.netprinter_debugmode == 'True':
                            print("Msw1 switches sent", flush=True)
                    case b'\x02':
                                # Respond with: Autocutter enabled and chinese character code GB2312.
                        response:bytes = b'\x31\x31\x31\x30\x30\x30\x30\x30'
                        self.wfile.write(b'\x37\x21' + response + b'\x00') 
                        self.wfile.flush()
                        if self.netprinter_debugmode == 'True':
                            print("Msw2 switches sent", flush=True)
                    case _:
                        if self.netprinter_debugmode == 'True':
                            print(f"Unknown switch set requested: {request}", flush=True)

            case b'\x06': #6
                        # Transmit the customized setting values
                a:bytes = self.rfile.read(1)  #read a
                request = request + a
                        
                response:bytes = b''
                match int.from_bytes(a):
                    case 1:
                                #NV Memory capacity
                        response = b'128'

                    case 2:
                                #NV graphics capacity
                        response = b'256'
                                
                    case 3:
                                #Paper width
                        response = b'80'
                                
                    case 5:
                                #Print density
                        response = b'72'
                            
                    case 6:
                                #Print speed
                        response = b'20'
                                
                    case 7:
                                #Thai print char mode
                        response = b'1'
                            
                    case 8:
                                #Code page
                        response = b'2' #PC850 Multilingual
                            
                    case 9:
                                # Default international character
                        response = b'\xB0' #wavy character
                                
                    case 10:
                                #Selection of the interface(???)
                        response = b'1'
                            
                    case 11:
                                #Column emulation mode (???)
                        response = b'1'
                                
                    case 12:
                                #Command execution (offline)(???)
                        response = b'0'
                            
                    case 13:
                                # Specification for the top margin
                        response = b'22'
                                
                    case 14:
                                #Selection of paper removal standby
                        response = b'0'
                                
                    case 20:
                                #Switchover time 
                        response = b'1'
                            
                    case 21:
                                #Selection of primary connection interface (???)
                        response = b'1'
                            
                    case 22:
                        response = b'1'    
                            
                    case 70|71|73:
                                # Graphics expansion and reduction ratios
                        response = b'1'
                            
                    case 97:
                        response = b'1'
                            
                    case 98:
                                #PSU output
                        response = b'112'
                                
                    case 100:
                        response = b'2'
                                
                    case 101:
                                #ARP: top margin
                        response = b'1'
                               
                    case 102:
                                #ARP: bottom margin
                        response = b'1'
                                    
                    case 103:
                                #ARP: line spacing
                        response = b'1'
                                
                    case 104:
                                #ARP: extra line feed spacing
                        response = b'1'
                                
                    case 105:
                                #ARP: barcode height
                        response = b'1'
                                
                    case 106:
                                #ARP: character height
                        response = b'1'
                                                            
                    case 111|112|113:
                                #Automatic replacement of fonts A,B,C
                        response = b'1'
                      
                    case num if num in range(116, 196):
                        # Model-specific values.
                        #We have to send something back, anything.
                        self.send_response_gs_parens_E_fn6(a, b'303')
                        
                        if self.netprinter_debugmode == 'True':
                            print(f"Model-specific customized setting requested: {a}", flush=True) 
                        
                        
                    case _:
                        if self.netprinter_debugmode == 'True':
                            print(f"Unknown customized setting requested: {a}", flush=True)   
                        
                if int.from_bytes(a) in [1,2,3,4,5,6,7,8,9,10,11,12,13,14,20,21,22,70,71,73,97,98,100,101,102,103,104,105,106,111,112,113]:
                    self.send_response_gs_parens_E_fn6(a, response)
                    if self.netprinter_debugmode == 'True':
                        print(f"Customized setting {a} sent", flush=True)
                        

            case b'\x0C': # 12
                """ NOTE: Transmit the configuration item for the serial interface.  Probably never happens over Ethernet"""
              
                #We need to send back two things "Header to NULL"
                # the received command (a), and the value.
                a:bytes = self.rfile.read(1)
                request = request + a
                
                le_a:bytes = int.to_bytes(ord(f'{int.from_bytes(a)}')) 
                
                value:bytes = b'19200' # up to 5 bytes, all numbers.
                
                response:bytes = b'\x37\x33' + le_a + b'\x1f'+ value + b'\x00'
                self.wfile.write(response)
                self.wfile.flush()
                
                if self.netprinter_debugmode == 'True':
                        print(f"Serial flow control command received: {request}", flush=True)
                

            case b'\x0E':  #14
                """NOTE: this one is for Bluetooth interface config.  Probably never happens over Ethernet"""
                
                #We need to send back two things "Header to NULL"
                # the received command (a), and the value.
                a:bytes = self.rfile.read(1)
                request = request + a
                
                value:bytes = b'19200' # up to 16 bytes, all numbers.
                
                response:bytes = b'\x37\x4a' + a + value + b'\x00'
                self.wfile.write(response)
                self.wfile.flush()
                
                
                if self.netprinter_debugmode == 'True':
                        print(f"Bluetooth interface config command received: {request}", flush=True)

            case b'\x10':  #16
                """NOTE: this one is for USB interface config.  Probably never happens over Ethernet"""
                
                # Read the received command (a)
                a:bytes = self.rfile.read(1)
                request = request + a
                
                #We send back a few bytes -> this should be an IEEE1284-compliant device ID (up to 1024 chars) or Class
                self.wfile.write(b'ESCPOS-netprinter')
                self.wfile.flush()
                
                if self.netprinter_debugmode == 'True':
                    print(f"USB interface config command received: {request}", flush=True)

            case b'\x32':  #50
                # Transmit the paper layout information
                n:bytes = self.rfile.read(1)  #read n
                request = request + n
                match n:
                    case b'\x40' | b'\x50':  #64 (set) or 80(actual)
                                #Setting values - only useful for labels so not used
                        le_n:bytes = str.encode(f'{int.from_bytes(n)}')
                        separator = b'\x1F'
                        sa = b'48' #Paper layout is not used
                        sb = b'' #Value omitted
                        sc = b'' #Value omitted
                        sd = b'' #Value omitted
                        se = b'' #Value omitted
                        sf = b'' #Value omitted
                        sg = b'' #Value omitted
                        sh = b'' #Value omitted
                        response:bytes = sa +separator+ sb +separator+ sc +separator+ sd +separator+ se +separator+ sf +separator+ sg +separator+ sh +separator
                        self.wfile.write(b'\x37\x39' + le_n + separator + response + b'\x00') 
                        self.wfile.flush()
                        if self.netprinter_debugmode == 'True':
                            print("Paper layout sent", flush=True)
                    case _:
                        if self.netprinter_debugmode == 'True':
                            print(f"Unknown paper layout info received: {request}", flush=True)

            case b'\x34': #52
                #Transmit the control settings for label paper
                #Not interested, so we send CAN after the first Media string block
                #get the block
                request = request + self.consume_parameter_data(pL, pH)
                #send CAN (24 in decimal)
                self.wfile.write(b'\x18') 
                self.wfile.flush()
                if self.netprinter_debugmode == 'True':
                    print(f"Label printer control settings received: {request}", flush=True)
                
            
            case b'\x64':  #100:
                        #Transmit internal buzzer patterns
                a:bytes = self.rfile.read(1)  #read a, the desired pattern
                request = request + a

                        # Extracted from the Epson docs:
                        # [n m1 t1 m2 t2 m3 t3 m4 t4 m5 t5 m6 t6] (13 bytes) is processed as one sound pattern. 
                        # When the setting of "Duration time" is (t = 0), it is 1-byte data of "0" [Hex = 30h / Decimal = 48].
                        # When the setting of "Duration time" is (t = 100), it is 3-byte data of "100" [Hex = 31h, 30h, 30h / Decimal = 49, 48, 48].
                        # NOTE: there is no mention in the spec for the m fields, so I will assume it's the same as t:  char-to-hex.

                        # Our pattern will be "silence for 0 seconds, 6 times"
                pattern = b'000000000000' 
                self.wfile.write(a + pattern + b'\x00')  #The data has to be sent "Header to NUL" with a as a header.
                self.wfile.flush()
                if self.netprinter_debugmode == 'True':
                    print("Buzzer pattern sent", flush=True)

            case _:
                        #Any other functions that do not transmit data back - we consume the parameter bytes.
                if self.netprinter_debugmode == 'True':
                    print(f"No-response-needed GS ( E command received: {request}", flush=True)
                request = request + self.consume_parameter_data(pL, pH)
        return request

    def send_response_gs_parens_E_fn6(self, a:bytes, response:bytes) -> None:
        """Helper to respond to a customized settings request ( GS ( E <fn=6> )

        Args:
            a (bytes): the request type
            response (bytes): the response number
        """        
        self.wfile.write(b'\x37\x27' + a + b'\x1F' + response + b'\x00') 
        self.wfile.flush()


    def respond_dle_eot(self) -> bytes:
        """Consume and process one DLE EOT command and return the processed bytes

        Returns:
            bytes: The consumed request
        """        
        if self.netprinter_debugmode == 'True':
            print("DLE EOT request", flush=True)
            
        request:bytes = self.rfile.read1(1)  #The ops are 1 or 2 bytes, check the first
        match request:
            case b'\x01':
                # Send printer status OK
                self.wfile.write(b'\x16') 
                self.wfile.flush()
                if self.netprinter_debugmode == 'True':
                    print("Printer status sent", flush=True)
                    
            case b'\x02' | b'\x03' | b'\x04':
                # Send b'\x12" all-clear for one-byte status requests
                self.wfile.write(b'\x12') 
                self.wfile.flush()
                if self.netprinter_debugmode == 'True':
                    print("b'x12' all-clear sent", flush=True)   
            
            case b'\x07' | b'\x08':
                #Send all-clear for 2-byte status requests
                
                #First, get the second byte
                request = request + self.rfile.read(1)
                
                # Send the all-clear
                self.wfile.write(b'\x12') 
                self.wfile.flush()
                if self.netprinter_debugmode == 'True':
                    print("Ink or peeler all-clear sent", flush=True)
                    
            case b'\x18':
                # Send normal interface status
                
                #First, get the second byte
                request = request + self.rfile.read(1)
                
                # Send the normal status
                self.wfile.write(b'\x10') 
                self.wfile.flush()
                if self.netprinter_debugmode == 'True':
                    print("Paper status sent", flush=True)
            
            case _:
                #Some other status has been requested, or we are lost in the byte stream.  Ignore the problem and hope for the best.
                pass

        return request
            
    def process_gs_parens_H(self) -> bytes:
        """Consume and process one GS ( H request and return the processed bytes

        Returns:
            bytes: The consumed request
        """        
        
        #Transmission + response or status (not for OPOS or Java POS, and very mysterious and printer-dependant)
        #Since it is printer-dependant, we will simply consume the data and continue.   The spec does not mention that this could block the print.
        
        if self.netprinter_debugmode == 'True':
            print("GS ( H request received")

        #  First, get the size and fn bytes
        pL:bytes = self.rfile.read(1) # Get pL value 
        pH:bytes = self.rfile.read(1) # Get pH value
        fn:bytes = self.rfile.read(1) # Get fn byte
                
        request:bytes = pL + pH + fn + self.consume_parameter_data(pL, pH)
        
        identifier:bytes = b''
        if fn==b'\x30': 
            identifier = b'\x22'
            
        elif fn==b'\x31': 
            identifier = b'\x23'
        else:
            if self.netprinter_debugmode == 'True':
                print(f"Unknown GS ( H function received: {fn}", flush=True) 
        
        self.wfile.write(b'\x37'+ identifier + b'1234' + b'\x00') #Send the response to the client
        self.wfile.flush()
       
        if self.netprinter_debugmode == 'True':
            print("Transmission of response or status done.", flush=True)
            
        return request


    def consume_parameter_data(self, pL:bytes, pH:bytes) -> bytes:
        """Consume parameter data without processing for a length specified by pL and pH

        WARNING:  if there are less than the expected number of bytes, the return will be shorter than expected.

        Args:
            pL (bytes): Low byte of the size 
            pH (bytes): High byte of the size

        Returns:
            bytes: The received bytes.
        """        
        num_bytes = self.calculate_param_size(pL, pH)
        
        parameter_data:bytes = b''
        if num_bytes == 0:
            print("Error:  zero-byte-long argument specified", flush=True)
        else:
            parameter_data =  self.rfile.read(num_bytes) # Send these bytes forward in all cases

        return parameter_data

    def calculate_param_size(self, pL:bytes, pH:bytes) -> int:
        """ Calculate the parameter data size from pL and pH

        Args:
            pL (bytes): Low byte of the size 
            pH (bytes): High byte of the size 

        Returns:
            int: size of the parameter in bytes
        """        
        # pL and pH specify the number of bytes following as (pL + (pH × 256)). 
        
        low:int = int.from_bytes(pL, "big")
        high:int = int.from_bytes(pH, "big")
        num_bytes:int = low + (high * 256) # Range:  1 - 65535

        return num_bytes

    def consume_byte_array(self, xL:bytes, xH:bytes, yL:bytes, yH:bytes) -> bytes:
        """Consume a byte array of a size defined by xL, xH, yL and yH

        Args:
            xL (bytes): Low byte of x size
            xH (bytes): High byte of x size
            yL (bytes): Low byte of y size
            yH (bytes): High byte of y size

        Returns:
            bytes: all the data for this array
        """        
        num_x = self.calculate_param_size(xL, xH)
        num_y = self.calculate_param_size(yL, yH)
        
        num_bytes = num_x * num_y * 8
        
        byte_array:bytes = b''
        if num_bytes == 0:
            print("Error:  zero-byte-long argument specified", flush=True)
        else:
            byte_array =  self.rfile.read(num_bytes) # Send these bytes forward in all cases
            
        return byte_array
        


    #Convertir l'impression recue en HTML et la rendre disponible à Flask
    # Implémente les blocs "Main processing" et "Mechanism" de l'APG Epson.
    def print_toHTML(self, binfile:BufferedWriter, bin_filename:PurePath):

        print("Printing ", binfile.name)
        try:
            if self.netprinter_debugmode == 'True':
                recu:CompletedProcess = subprocess.run(["php", "esc2html.php", "--debug", bin_filename.as_posix()], capture_output=True, text=True, encoding='utf-8', errors='replace', check=True)
            else:
                recu:CompletedProcess = subprocess.run(["php", "esc2html.php", bin_filename.as_posix()], capture_output=True, text=True, encoding='utf-8', errors='replace', check=True)

        except subprocess.CalledProcessError as err:
            print(f"Error while converting receipt: {err.returncode}")
            # append the error output to the log file
            with open(PurePath('web','tmp', 'esc2html_log'), mode='at') as log:
                log.write(f"Error while converting a JetDirect print: {err.returncode}")
                log.write(datetime.now(tz=ZoneInfo(os.environ['ESCPOS_TIMEZONE'])).strftime('%Y%b%d %X.%f %Z'))
                log.write(err.stderr)
                log.close()
            
            print("Error output:")
            print(err.stderr, flush=True)
        
        else:
            #Si la conversion s'est bien passée, on devrait avoir le HTML
            print (f"Receipt decoded", flush=True)
            with open(PurePath('web','tmp', 'esc2html_log'), mode='at') as log:
                log.write("Successful JetDirect print\n")
                log.write(datetime.now(tz=ZoneInfo(os.environ['ESCPOS_TIMEZONE'])).strftime('%Y%b%d %X.%f %Z\n\n'))
                log.write(recu.stderr)
                log.close()
            #print(recu.stdout, flush=True)

            #Ajouter un titre au reçu
            heureRecept = datetime.now(tz=ZoneInfo(os.environ['ESCPOS_TIMEZONE']))
            recuConvert = self.add_html_title(heureRecept, recu.stdout)

            #print(etree.tostring(theHead), flush=True)

            try:
                #Créer un nouveau fichier avec le nom du reçu
                html_filename = 'receipt{}.html'.format(heureRecept.strftime('%Y%b%d_%X.%f%Z'))
                with open(PurePath('web', 'receipts', html_filename), mode='wt') as nouveauRecu:
                    #Écrire le reçu dans le fichier.
                    nouveauRecu.write(recuConvert)
                    nouveauRecu.close()
                    #Ajouter le reçu à la liste des reçus
                    self.add_receipt_to_directory(html_filename)

            except OSError as err:
                print("File creation error:", err.errno, flush=True)

    @staticmethod
    def add_html_title(heureRecept:datetime, recu:str, self=None)->str:
        """ Ajouter un titre au reçu """
        recuConvert:etree.ElementTree  = html.fromstring(recu)

        theHead:etree.Element = recuConvert.head
        newTitle = etree.Element("title")
        newTitle.text = "Reçu imprimé le {}".format(heureRecept.strftime('%d %b %Y @ %X%Z'))
        theHead.append(newTitle)

        return html.tostring(recuConvert).decode()
    
    @staticmethod
    def add_receipt_to_directory(new_filename: str, self=None) -> None:
        # Add an entry in the reference file with the new filename and an unique ID.
        # Open the CSV file in read mode to count the existing rows
        try:
            with open(PurePath('web', 'receipt_list.csv'), mode='r') as fileDirectory:
                reader = csv.reader(fileDirectory)
                # Count the number of rows, starting from 1 (to include the header)
                next_fileID = sum(1 for row in reader) + 1
                fileDirectory.close()
        except FileNotFoundError:
            # Create the CSV file with the headers
            with open(PurePath('web', 'receipt_list.csv'), mode='w', newline='') as fileDirectory:
                writer = csv.writer(fileDirectory)
                writer.writerow(['next_fileID', 'filename'])
                fileDirectory.close()
            next_fileID = 1  # If the file does not exist, start IDs is 1
        # Now, id holds the next sequential ID

        # Open the CSV file in append mode to add a new row
        with open(PurePath('web', 'receipt_list.csv'), mode='a', newline='') as fileDirectory:
            writer = csv.writer(fileDirectory)
            # Append a new line to the CSV file with the new ID and filename
            writer.writerow([next_fileID, new_filename])    
               

## Printer UI

# Flask startup
app = Flask(__name__)

# Babel setup

def get_locale() -> str | None:
    lang = request.cookies.get('lang')
    if lang in babel_config.Config.LANGUAGES :
        return lang
    else :
        return request.accept_languages.best_match(babel_config.Config.LANGUAGES)

babel = Babel(app, locale_selector=get_locale)

@app.context_processor
def inject_conf_var():
    return dict(AVAILABLE_LANGUAGES=babel_config.Config.LANGUAGES,
                CURRENT_LANGUAGE=get_locale())

@app.route('/language=<language>')
def set_language(language=None):
    resp = redirect(url_for('accueil'))
    # Check if the desired translation is available.  If not, get the best match to what the browser desires. 
    if language in babel_config.Config.LANGUAGES:
        resp.set_cookie('lang', language)
    else:
        resp.set_cookie('lang', request.accept_languages.best_match(babel_config.Config.LANGUAGES) ) # Ignore the request and guess the preferred language of the browser.
    return resp


# Flask routes for the UI
@app.route("/")
def accueil():
    return render_template('accueil.html.j2', host = request.host.split(':')[0], 
                           jetDirectPort=getenv('PRINTER_PORT', '9100'),
                            debug=getenv('FLASK_RUN_DEBUG', "false") )

@app.route("/recus")
def list_receipts():
    """ List all the receipts available """
    try:
        with open(PurePath('web', 'receipt_list.csv'), mode='r') as fileDirectory:
            # Skip the header and get all the filenames in a list
            reader = csv.reader(fileDirectory)
            noms = list()
            for row in reader:
                if row[0] == 'next_fileID':
                    continue # Skip the header
                else:
                    # Add the file id and filename to the list
                    noms.append([row[0], row[1]])
            # Since the file is found, render the template with the list of filenames
            # in reverse chronological order (most recent at the top)
            noms.reverse()
            return render_template('receiptList.html.j2', receiptlist=noms)
    except FileNotFoundError:
        return redirect(url_for('accueil'))
    

@app.route("/recus/<int:fileID>")
def show_receipt(fileID:int):
    """ Show the receipt with the given ID """
    # Open the CSV file in read mode
    with open(PurePath('web', 'receipt_list.csv'), mode='r') as fileDirectory:
        reader = csv.reader(fileDirectory)
        # Find the row with the given ID
        for row in reader:
            if row[0] == 'next_fileID':
                continue # Skip the header
            elif int(row[0]) == fileID:
                filename = row[1]
                break
        else:
            # If the ID is not found, return a 404 error
            return "Not found", 404
        
        # If the ID is found, open the html rendering of the receipt and add the footer from templates/footer.html
        with open(PurePath('web', 'receipts', filename), mode='rt') as receipt:
            receipt_html = receipt.read()   # Read the file content
            receipt_html = receipt_html.replace('<body>', '<body style="display: flex;flex-direction: column;min-height: 100vh;"><div id="page" style="flex-grow: 1;">')
            receipt_html = receipt_html.replace('</body>', '</div>' + render_template('footer.html.j2') + '</body>')  # Append the footer
            return receipt_html
    

@app.route("/newReceipt")
def publish_receipt_from_CUPS():
    """ Get the receipt from the CUPS temp directory and publish it in the web/receipts directory and add the corresponding log to our permanent logfile"""
    heureRecept = datetime.now(tz=ZoneInfo(os.environ['ESCPOS_TIMEZONE']))  #TODO:  make this configurable from the dockerfile.
    #NOTE: on set dans cups-files.conf le répertoire TempDir:   
    #Extraire le répertoire temporaire de CUPS de cups-files.conf
    source_dir=PurePath('/var', 'spool', 'cups', 'tmp')
    
    # Get the source filename from the environment variable and create the full path
    source_filename = os.environ['DEST_FILENAME']
    source_file = source_dir.joinpath(source_filename)

    # specify the destination filename
    new_filename = 'receipt{}.html'.format(heureRecept.strftime('%Y%b%d_%X.%f%Z'))

    # Create the full destination path with the new filename
    destination_file = PurePath('web', 'receipts', new_filename)

    # Read the source file, add the title and write it in the destination file
    with open(source_file, mode='rt') as receipt:
        receipt_html = receipt.read()
        receipt_html = ESCPOSHandler.add_html_title(heureRecept, receipt_html)
        with open(destination_file, mode='wt') as newReceipt:
            newReceipt.write(receipt_html)
            newReceipt.close()

    # Add the new receipt to the directory
    ESCPOSHandler.add_receipt_to_directory(new_filename)

    #Load the log file from /var/spool/cups/tmp/ and append it in web/tmp/esc2html_log
    logfile_filename = os.environ['LOG_FILENAME']
    # print(logfile_filename)
    log = open(PurePath('web','tmp', 'esc2html_log'), mode='a')
    source_log = open(source_dir.joinpath(logfile_filename), mode='rt')
    log.write(f"CUPS print received at {datetime.now(tz=ZoneInfo(os.environ['ESCPOS_TIMEZONE'])).strftime('%Y%b%d %X.%f %Z')}\n")
    log.write(source_log.read())
    log.close()
    source_log.close()

    #send an http acknowledgement
    return "OK"

## End printer UI




def launchPrintServer(printServ:ESCPOSServer):
    #Recevoir des connexions, une à la fois, pour l'éternité.  Émule le protocle HP JetDirect
    """ NOTE: On a volontairement pris la version bloquante pour s'assurer que chaque reçu va être sauvegardé puis converti avant d'en accepter un autre.
        NOTE:  il est possible que ce soit le comportement attendu de n'accepter qu'une connection à la fois.  Voir p.6 de la spécification d'un module Ethernet
                à l'adresse suivante:  https://files.cyberdata.net/assets/010748/ETHERNET_IV_Product_Guide_Rev_D.pdf  """
    print (f"JetDirect port open", flush=True)
    printServ.serve_forever()


if __name__ == "__main__":

    #Obtenir les variables d'environnement
    host = getenv('FLASK_RUN_HOST', '0.0.0.0')  #By default, listen to all source addresses
    port = getenv('FLASK_RUN_PORT', '5000')
    flask_debugmode = getenv('FLASK_RUN_DEBUG', "false")
    printPort = getenv('PRINTER_PORT', '9100')

    print("Starting ESCPOS-netprinter", flush=True)

    #Lancer le service d'impression TCP
    with ESCPOSServer((host, int(printPort)), ESCPOSHandler) as printServer:
        t = threading.Thread(target=launchPrintServer, args=[printServer])
        t.daemon = True
        t.start()
    
        #Lancer l'application Flask
        if flask_debugmode == 'True': 
            startDebug:bool = True
        else:
            startDebug:bool = False

        app.run(host=host, port=int(port), debug=startDebug, use_reloader=False) #On empêche le reloader parce qu'il repart "main" au complet et le service d'imprimante n'est pas conçue pour ça.
