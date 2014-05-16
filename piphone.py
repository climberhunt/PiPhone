# PiPhone - A DIY Cellphone based on Raspberry Pi
# This must run as root (sudo python lapse.py) due to framebuffer, etc.
#
# http://www.adafruit.com/products/998  (Raspberry Pi Model B)
# http://www.adafruit.com/products/1601 (PiTFT Mini Kit)
#
# Prerequisite tutorials: aside from the basic Raspbian setup and PiTFT setup
# http://learn.adafruit.com/adafruit-pitft-28-inch-resistive-touchscreen-display-raspberry-pi
#
# piphone.py by David Hunt (dave@davidhunt.ie)
# based on cam.py by Phil Burgess / Paint Your Dragon for Adafruit Industries.
# BSD license, all text above must be included in any redistribution.

import atexit
import cPickle as pickle
import errno
import fnmatch
import io
import os
import pygame
import threading
from pygame.locals import *
from subprocess import call  
from time import sleep
from datetime import datetime, timedelta
import serial


# UI classes ---------------------------------------------------------------

# Icon is a very simple bitmap class, just associates a name and a pygame
# image (PNG loaded from icons directory) for each.
# There isn't a globally-declared fixed list of Icons.  Instead, the list
# is populated at runtime from the contents of the 'icons' directory.

class Icon:

	def __init__(self, name):
	  self.name = name
	  try:
	    self.bitmap = pygame.image.load(iconPath + '/' + name + '.png')
	  except:
	    pass

# Button is a simple tappable screen region.  Each has:
#  - bounding rect ((X,Y,W,H) in pixels)
#  - optional background color and/or Icon (or None), always centered
#  - optional foreground Icon, always centered
#  - optional single callback function
#  - optional single value passed to callback
# Occasionally Buttons are used as a convenience for positioning Icons
# but the taps are ignored.  Stacking order is important; when Buttons
# overlap, lowest/first Button in list takes precedence when processing
# input, and highest/last Button is drawn atop prior Button(s).  This is
# used, for example, to center an Icon by creating a passive Button the
# width of the full screen, but with other buttons left or right that
# may take input precedence (e.g. the Effect labels & buttons).
# After Icons are loaded at runtime, a pass is made through the global
# buttons[] list to assign the Icon objects (from names) to each Button.

class Button:

	def __init__(self, rect, **kwargs):
	  self.rect     = rect # Bounds
	  self.color    = None # Background fill color, if any
	  self.iconBg   = None # Background Icon (atop color fill)
	  self.iconFg   = None # Foreground Icon (atop background)
	  self.bg       = None # Background Icon name
	  self.fg       = None # Foreground Icon name
	  self.callback = None # Callback function
	  self.value    = None # Value passed to callback
	  for key, value in kwargs.iteritems():
	    if   key == 'color': self.color    = value
	    elif key == 'bg'   : self.bg       = value
	    elif key == 'fg'   : self.fg       = value
	    elif key == 'cb'   : self.callback = value
	    elif key == 'value': self.value    = value

	def selected(self, pos):
	  x1 = self.rect[0]
	  y1 = self.rect[1]
	  x2 = x1 + self.rect[2] - 1
	  y2 = y1 + self.rect[3] - 1
	  if ((pos[0] >= x1) and (pos[0] <= x2) and
	      (pos[1] >= y1) and (pos[1] <= y2)):
	    if self.callback:
	      if self.value is None: self.callback()
	      else:                  self.callback(self.value)
	    return True
	  return False

	def draw(self, screen):
	  if self.color:
	    screen.fill(self.color, self.rect)
	  if self.iconBg:
	    screen.blit(self.iconBg.bitmap,
	      (self.rect[0]+(self.rect[2]-self.iconBg.bitmap.get_width())/2,
	       self.rect[1]+(self.rect[3]-self.iconBg.bitmap.get_height())/2))
	  if self.iconFg:
	    screen.blit(self.iconFg.bitmap,
	      (self.rect[0]+(self.rect[2]-self.iconFg.bitmap.get_width())/2,
	       self.rect[1]+(self.rect[3]-self.iconFg.bitmap.get_height())/2))

	def setBg(self, name):
	  if name is None:
	    self.iconBg = None
	  else:
	    for i in icons:
	      if name == i.name:
	        self.iconBg = i
	        break

# UI callbacks -------------------------------------------------------------
# These are defined before globals because they're referenced by items in
# the global buttons[] list.


def numericCallback(n): # Pass 1 (next setting) or -1 (prev setting)
	global screenMode
	global numberstring
	global phonecall
	if n < 10 and screenMode == 0:
		numberstring = numberstring + str(n)
	elif n == 10 and screenMode == 0:
		numberstring = numberstring[:-1]
	elif n == 12:
		#if phonecall == 0:
		if screenMode == 0:
			if len(numberstring) > 0:
				print("Calling " + numberstring);
				serialport.write("AT\r")
				response = serialport.readlines(None)
				serialport.write("ATD " + numberstring + ';\r')
				response = serialport.readlines(None)
				print response
				#phonecall = 1
				screenMode = 1
		else:
			print("Hanging Up...")
			serialport.write("AT\r")
			response = serialport.readlines(None)
			serialport.write("ATH\r")
			response = serialport.readlines(None)
			print response
			#phonecall = 0
			screenMode = 0
		if len(numberstring) > 0:
			numeric = int(numberstring)
			v[dict_idx] = numeric



# Global stuff -------------------------------------------------------------

busy            = False
threadExited    = False
screenMode      =  0      # Current screen mode; default = viewfinder
phonecall       =  1
screenModePrior = -1      # Prior screen mode (for detecting changes)
iconPath        = 'icons' # Subdirectory containing UI bitmaps (PNG format)
numeric         = 0       # number from numeric keypad      
numberstring	= ""
motorRunning	= 0
motorDirection	= 0
returnScreen   = 0
shutterpin     = 17
motorpinA      = 18
motorpinB      = 27
motorpin       = motorpinA
currentframe   = 0
framecount     = 100
settling_time  = 0.2
shutter_length = 0.2
interval_delay = 0.2
dict_idx	   = "Interval"
v = { "Pulse": 100,
	"Interval": 3000,
	"Images": 150}

icons = [] # This list gets populated at startup

# buttons[] is a list of lists; each top-level list element corresponds
# to one screen mode (e.g. viewfinder, image playback, storage settings),
# and each element within those lists corresponds to one UI button.
# There's a little bit of repetition (e.g. prev/next buttons are
# declared for each settings screen, rather than a single reusable
# set); trying to reuse those few elements just made for an ugly
# tangle of code elsewhere.

buttons = [

  # Screen 0 for numeric input
  [Button(( 30,  0,320, 60), bg='box'),
   Button(( 30, 60, 60, 60), bg='1',     cb=numericCallback, value=1),
   Button(( 90, 60, 60, 60), bg='2',     cb=numericCallback, value=2),
   Button((150, 60, 60, 60), bg='3',     cb=numericCallback, value=3),
   Button(( 30,110, 60, 60), bg='4',     cb=numericCallback, value=4),
   Button(( 90,110, 60, 60), bg='5',     cb=numericCallback, value=5),
   Button((150,110, 60, 60), bg='6',     cb=numericCallback, value=6),
   Button(( 30,160, 60, 60), bg='7',     cb=numericCallback, value=7),
   Button(( 90,160, 60, 60), bg='8',     cb=numericCallback, value=8),
   Button((150,160, 60, 60), bg='9',     cb=numericCallback, value=9),
   Button(( 30,210, 60, 60), bg='star',  cb=numericCallback, value=0),
   Button(( 90,210, 60, 60), bg='0',     cb=numericCallback, value=0),
   Button((150,210, 60, 60), bg='hash',  cb=numericCallback, value=0),
   Button((180,260, 60, 60), bg='del2',  cb=numericCallback, value=10),
   Button(( 90,260, 60, 60), bg='call',    cb=numericCallback, value=12)],
  # Screen 1 for numeric input
  [Button(( 30,  0,320, 60), bg='box'),
   Button(( 90,260, 60, 60), bg='hang',    cb=numericCallback, value=12)]
]


# Assorted utility functions -----------------------------------------------


def saveSettings():
	global v
	try:
	  outfile = open('piphone.pkl', 'wb')
	  # Use a dictionary (rather than pickling 'raw' values) so
	  # the number & order of things can change without breaking.
	  pickle.dump(v, outfile)
	  outfile.close()
	except:
	  pass

def loadSettings():
	global v
	try:
	  infile = open('piphone.pkl', 'rb')
	  v = pickle.load(infile)
	  infile.close()
	except:
	  pass



# Initialization -----------------------------------------------------------

# Init framebuffer/touchscreen environment variables
os.putenv('SDL_VIDEODRIVER', 'fbcon')
os.putenv('SDL_FBDEV'      , '/dev/fb1')
os.putenv('SDL_MOUSEDRV'   , 'TSLIB')
os.putenv('SDL_MOUSEDEV'   , '/dev/input/touchscreen')


# Init pygame and screen
print "Initting..."
pygame.init()
print "Setting Mouse invisible..."
pygame.mouse.set_visible(False)
print "Setting fullscreen..."
modes = pygame.display.list_modes(16)
screen = pygame.display.set_mode(modes[0], FULLSCREEN, 16)

print "Loading Icons..."
# Load all icons at startup.
for file in os.listdir(iconPath):
  if fnmatch.fnmatch(file, '*.png'):
    icons.append(Icon(file.split('.')[0]))
# Assign Icons to Buttons, now that they're loaded
print"Assigning Buttons"
for s in buttons:        # For each screenful of buttons...
  for b in s:            #  For each button on screen...
    for i in icons:      #   For each icon...
      if b.bg == i.name: #    Compare names; match?
        b.iconBg = i     #     Assign Icon to Button
        b.bg     = None  #     Name no longer used; allow garbage collection
      if b.fg == i.name:
        b.iconFg = i
        b.fg     = None


print"Load Settings"
loadSettings() # Must come last; fiddles with Button/Icon states

print "loading background.."
img    = pygame.image.load("icons/PiPhone.png")

if img is None or img.get_height() < 240: # Letterbox, clear background
  screen.fill(0)
if img:
  screen.blit(img,
    ((240 - img.get_width() ) / 2,
     (320 - img.get_height()) / 2))
pygame.display.update()
sleep(2)

print "Initialising Modem.."
serialport = serial.Serial("/dev/ttyAMA0", 115200, timeout=0.5)
serialport.write("AT\r")
response = serialport.readlines(None)
serialport.write("ATE0\r")
response = serialport.readlines(None)
serialport.write("AT\r")
response = serialport.readlines(None)
print response



# Main loop ----------------------------------------------------------------



print "mainloop.."
while(True):

  # Process touchscreen input
  while True:
    screen_change = 0
    for event in pygame.event.get():
      if(event.type is MOUSEBUTTONDOWN):
        pos = pygame.mouse.get_pos()
        for b in buttons[screenMode]:
          if b.selected(pos): break
        screen_change = 1


    #if screenMode >= 1 or screenMode != screenModePrior: break
    if screen_change == 1 or screenMode != screenModePrior: break

  if img is None or img.get_height() < 240: 
    screen.fill(0)
  if img:
    screen.blit(img,
      ((240 - img.get_width() ) / 2,
       (320 - img.get_height()) / 2))

  # Overlay buttons on display and update
  for i,b in enumerate(buttons[screenMode]):
    b.draw(screen)
  if screenMode == 0 :
    myfont = pygame.font.SysFont("Arial", 40)
    label = myfont.render(numberstring, 1, (255,255,255))
    screen.blit(label, (10, 2))
  else:
    myfont = pygame.font.SysFont("Arial", 35)
    label = myfont.render("Calling", 1, (255,255,255))
    screen.blit(label, (10, 80))
    myfont = pygame.font.SysFont("Arial", 35)
    label = myfont.render(numberstring + "...", 1, (255,255,255))
    screen.blit(label, (10, 120))

  pygame.display.update()

  screenModePrior = screenMode

