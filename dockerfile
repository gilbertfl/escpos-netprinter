#On part de l'image Debian de php
FROM php:8.1-cli

#On va utiliser l'utilitaire "install-php-extensions" au lieu de PECL car il marche mieux.
#Voir:  https://github.com/mlocati/docker-php-extension-installer
ADD https://github.com/mlocati/docker-php-extension-installer/releases/latest/download/install-php-extensions /usr/local/bin/
RUN chmod +x /usr/local/bin/install-php-extensions
RUN install-php-extensions imagick @composer mbstring

#Note:  utiliser "." au lieu de * permet de garder la structure et envoyer tous les sous-répertoires
ADD . /home/escpos-emu/
WORKDIR /home/escpos-emu/

#Installation de Flask
RUN apt-get update
RUN apt-get install -y python3-flask 
RUN apt-get install -y python3-lxml

#Installation de php-qrcode :requiert seulement imagick
#RUN composer require chillerlan/php-qrcode:"^4.3.4" --prefer-stable
#RUN composer require chillerlan/php-qrcode:"5.0-beta"  
RUN composer install
RUN rm composer.json && rm composer.lock

#Configurer l'environnement d'exécution 
ENV FLASK_APP=escpos-netprinter.py
ENV FLASK_RUN_HOST=0.0.0.0
ENV FLASK_RUN_PORT=5000
ENV PRINTER_PORT=9100  
# To activate the Flask debug mode, set at True (case-sensitive)
ENV FLASK_RUN_DEBUG=false  

EXPOSE ${PRINTER_PORT}
EXPOSE ${FLASK_RUN_PORT}

# Démarrer le serveur Flask et le serveur d'impression
CMD python3 ${FLASK_APP}
