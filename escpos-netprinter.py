import os
from flask import Flask, redirect, render_template, request, url_for
from os import getenv
from io import BufferedWriter
import csv
import subprocess
from subprocess import CompletedProcess
from pathlib import PurePath
from lxml import html, etree
from datetime import datetime
from zoneinfo import ZoneInfo

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
        TODO:  peut-être implémenter certains codes de statut plus tard.  Voir l'APG Epson section "Processing the Data Received from the Printer"
    """
    timeout = 10  #On abandonne une réception après 10 secondes - un compromis pour assurer que tout passe sans se bourrer de connections zombies.
    
    # Receive the print data and dump it in a file.
    def handle(self):
        print (f"Address connected: {self.client_address}", flush=True)
        bin_filename = PurePath('web', 'tmp', "reception.bin")
        binfile = open(bin_filename, "wb")

        #Read everything until we get EOF 
        indata:bytes = b''
        try:
            indata = self.rfile.read()
     
        except TimeoutError:
            print("Timeout while reading")
            self.connection.close()
            if len(indata) > 0:
                print(f"{len(indata)} bytes received.")
                print(indata, flush=True)
            else: 
                print("Nothing received!", flush=True)
            
                
        else:
            print(f"{len(indata)} bytes received.", flush=True)
            #Écrire les données reçues dans le fichier.
            binfile.write(indata)

            #Quand on a reçu le signal de fin de transmission
            binfile.close()  #Écrire le fichier et le fermer

            self.wfile.write(b"ESCPOS-netprinter: All done!")  #A enlever plus tard?  On dit au client qu'on a fini.
            self.wfile.flush()
            self.connection.close()

            print ("Data received, signature sent.", flush=True)
            
            #traiter le fichier reception.bin pour en faire un HTML
            self.print_toHTML(binfile, bin_filename)

    #Convertir l'impression recue en HTML et la rendre disponible à Flask
    def print_toHTML(self, binfile:BufferedWriter, bin_filename:PurePath):

        print("Printing ", binfile.name)
        recu:CompletedProcess = subprocess.run(["php", "esc2html.php", bin_filename.as_posix()], capture_output=True, text=True )
        if recu.returncode != 0:
            print(f"Error while converting receipt: {recu.returncode}")
            print("Error output:")
            print(recu.stderr, flush=True)
        
        else:
            #Si la conversion s'est bien passée, on devrait avoir le HTML
            print (f"Receipt decoded", flush=True)
            #print(recu.stdout, flush=True)

            #Ajouter un titre au reçu
            heureRecept = datetime.now(tz=ZoneInfo("Canada/Eastern"))
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
               

app = Flask(__name__)

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
        
        # If the ID is found, open the file to append the footer from templates/footer.html
        with open(PurePath('web', 'receipts', filename), mode='rt') as receipt:
            receipt_html = receipt.read()   # Read the file content
            receipt_html = receipt_html.replace('</body>', render_template('footer.html') + '</body>')  # Append the footer
            return receipt_html
    

@app.route("/newReceipt")
def publish_receipt_from_CUPS():
    """ Get the receipt from the CUPS temp directory and publish it in the web/receipts directory and add the corresponding log to our permanent logfile"""
    heureRecept = datetime.now(tz=ZoneInfo("Canada/Eastern"))
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
    print(logfile_filename)
    log = open(PurePath('web','tmp', 'esc2html_log'), mode='at')
    source_log = open(source_dir.joinpath(logfile_filename), mode='rt')
    log.write(source_log.read())
    log.close()
    #remove the contents from the source log
    source_log.close()
    source_log = open(source_dir.joinpath('esc2html_log'), mode='wt')
    source_log.write('')
    source_log.close()

    #send an http acknowledgement
    return "OK"


def launchPrintServer(printServ:ESCPOSServer):
    #Recevoir des connexions, une à la fois, pour l'éternité.  Émule le protocle HP JetDirect
    """ NOTE: On a volontairement pris la version bloquante pour s'assurer que chaque reçu va être sauvegardé puis converti avant d'en accepter un autre.
        NOTE:  il est possible que ce soit le comportement attendu de n'accepter qu'une connection à la fois.  Voir p.6 de la spécification d'un module Ethernet
                à l'adresse suivante:  https://files.cyberdata.net/assets/010748/ETHERNET_IV_Product_Guide_Rev_D.pdf  """
    print (f"Printer port open", flush=True)
    printServ.serve_forever()


if __name__ == "__main__":

    #Obtenir les variables d'environnement
    host = getenv('FLASK_RUN_HOST', '0.0.0.0')  #By default, listen to all source addresses
    port = getenv('FLASK_RUN_PORT', '5000')
    debugmode = getenv('FLASK_RUN_DEBUG', "false")
    printPort = getenv('PRINTER_PORT', '9100')

    #Lancer le service d'impression TCP
    with ESCPOSServer((host, int(printPort)), ESCPOSHandler) as printServer:
        t = threading.Thread(target=launchPrintServer, args=[printServer])
        t.daemon = True
        t.start()
    
        #Lancer l'application Flask
        if debugmode == 'True': 
            startDebug:bool = True
        else:
            startDebug:bool = False

        app.run(host=host, port=int(port), debug=startDebug, use_reloader=False) #On empêche le reloader parce qu'il repart "main" au complet et le service d'imprimante n'est pas conçue pour ça.