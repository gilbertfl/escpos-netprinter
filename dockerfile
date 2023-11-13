#On part de l'image php-cli "latest" sur Debian
FROM php:cli

#On va utiliser l'utilitaire "install-php-extensions" au lieu de PECL car il marche mieux.
#Voir:  https://github.com/mlocati/docker-php-extension-installer
ADD https://github.com/mlocati/docker-php-extension-installer/releases/latest/download/install-php-extensions /usr/local/bin/
RUN chmod +x /usr/local/bin/install-php-extensions
RUN install-php-extensions mbstring @composer imagick

#Note:  utiliser "." au lieu de * permet de garder la structure et envoyer tous les sous-répertoires
ADD . /home/escpos-emu/
ADD --chmod=0555 cups/esc2file.sh /usr/lib/cups/backend/esc2file
WORKDIR /home/escpos-emu/

#Installation de Flask
RUN apt-get update
RUN apt-get install -y python3-flask 
RUN apt-get install -y python3-lxml

#Installation de CUPS
RUN apt-get install -y cups

#Configuration de CUPS   ATTENTION: on rend CUPS complètement ouvert de cette façon! 
RUN /usr/sbin/cupsd \
  && while [ ! -f /var/run/cups/cupsd.pid ]; do sleep 1; done \
  && cupsctl --remote-admin --remote-any --share-printers \
  && kill $(cat /var/run/cups/cupsd.pid)
RUN rm /etc/cups/snmp.conf


#Installation HTML printer
RUN composer install
RUN rm composer.json && rm composer.lock

#Configurer l'environnement d'exécution 
ENV FLASK_APP=escpos-netprinter.py
ENV FLASK_RUN_HOST=0.0.0.0
ENV FLASK_RUN_PORT=5000
ENV PRINTER_PORT=9100  

# "Device URI" for CUPS
ENV DEVICE_URI=esc2file:/home/escpos-emu/web/tmp/receipt.bin
# Temporary directory for CUPS
ENV TMPDIR=/home/escpos-emu/web/tmp/

# To activate the Flask debug mode, set at True (case-sensitive)
ENV FLASK_RUN_DEBUG=false  

EXPOSE ${PRINTER_PORT}
EXPOSE ${FLASK_RUN_PORT}
#Expose the CUPS admin port (temporary?)
EXPOSE 631

# Démarrer le serveur Flask et le serveur d'impression
CMD ["/usr/sbin/cupsd", "-f"]
#CMD python3 ${FLASK_APP}
#CMD ["/bin/bash","-c","./start.sh"]
