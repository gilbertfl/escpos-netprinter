#On part de l'image php-cli "latest" sur Debian
#FROM php:cli
FROM php:8.4-cli

#On va utiliser l'utilitaire "install-php-extensions" au lieu de PECL car il marche mieux.
#Voir:  https://github.com/mlocati/docker-php-extension-installer
ADD --chmod=0755 https://github.com/mlocati/docker-php-extension-installer/releases/latest/download/install-php-extensions /usr/local/bin/

#Installer les prérequis chillerlan/php-qrcode: composer, mbstring, imagick
RUN install-php-extensions mbstring @composer imagick

#Install Flask
RUN apt-get update
RUN apt-get install -y python3-flask 
RUN apt-get install -y python3-flask-babel
RUN apt-get install -y python3-lxml

#Install CUPS
RUN apt-get install -y cups

#Manage CUPS-specific users and permissions
RUN groupadd cups-admins
RUN useradd -d /home/escpos-emu -g cups-admins -s /sbin/nologin cupsadmin 
RUN echo "cupsadmin:123456" | chpasswd

#Installation de l'émulateur d'imprimante
#Note:  utiliser "." au lieu de * permet de garder la structure et envoyer tous les sous-répertoires
ADD . /home/escpos-emu/
ADD --chmod=0555 ./start.sh /home/escpos-emu/start.sh
RUN rm -rf web
ADD --chmod=0555 cups/esc2file.sh /usr/lib/cups/backend/esc2file
WORKDIR /home/escpos-emu/

#Configure CUPS
ADD cups/cupsd.conf /etc/cups/cupsd.conf 
ADD cups/cups-files.conf /etc/cups/cups-files.conf 
RUN rm /etc/cups/snmp.conf
RUN rm /home/escpos-emu/cups/cups-files.conf

#Installation HTML converter
RUN composer install --no-dev
RUN rm composer.json && rm composer.lock

#Configurer l'environnement d'exécution 
ENV FLASK_APP=escpos-netprinter.py
#Accepted source IP addresses
ENV FLASK_RUN_HOST=0.0.0.0
#Web interface port
ENV FLASK_RUN_PORT=80  
#This port is for the Jetdirect protocol.
ENV PRINTER_PORT=9100  

# To activate the Flask debug mode, set at True (case-sensitive)
ENV FLASK_RUN_DEBUG=false  
# To activate the netprinter debug mode, set at True (case-sensitive)
ENV ESCPOS_DEBUG=false

#Localization support environment variables
ENV ESCPOS_TIMEZONE="America/Montreal"


# Expose all necessary ports
EXPOSE ${PRINTER_PORT}
EXPOSE ${FLASK_RUN_PORT}
#Expose the lpd port
EXPOSE 515
#Expose the CUPS admin port
EXPOSE 631

# Compose the "Device URI" for CUPS  "esc2file:/dest_filename.suffix/log_filename.suffix/isdebug"
ENV DEST_FILENAME=esc2html.html
ENV LOG_FILENAME=esc2html_log
ENV DEVICE_URI=esc2file:/${DEST_FILENAME}/${LOG_FILENAME}/${ESCPOS_DEBUG}

# Start Flask and all printing services
CMD ["/bin/bash","-c","./start.sh"]
