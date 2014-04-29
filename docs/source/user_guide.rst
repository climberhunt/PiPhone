User Guide
============

PiPhone - A DIY Cellphone based on Raspberry Pi by `David Hunt <http://www.davidhunt.ie>`_.

To get piphone.py to start at boot, we need to add a couple of lines to the /etc/rc.local file::

    sudo nano /etc/rc.local

and add the following lines to the end, assuming you've installed the software in /home/pi/PyPhone::

    cd /home/pi/PiPhone
    python piphone.py &

Then, when you boot the Raspberry Pi, you should go straight into the PiPhone dialler screen. Just dial a number and go!



