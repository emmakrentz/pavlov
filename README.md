# Pavlov's Piano

Just a piano that sprays you in the face if you play the notes incorrectly. 

Simple explanation:
MIDI-enabled keyboard sends signals via direct connection which are interpretable through pygame.
MusicXML files are sheet music that can be read in Python through music21 package.
By combining the two, we can download a piece of sheet music and play along and have our code verify that we are playing correctly.
Adding in an Arduino, a servo, and a spray bottle, we spray the user in the face if they play incorrectly.
