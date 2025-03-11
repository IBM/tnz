---
title: File Transfer
hide:
  - toc
---

## Upload a File from PC to Mainframe

1. Log into TSO session
2. Go to READY prompt (exit ISPF)
3. Enter command:  `IND$FILE PUT CLEANUP.PROC ASCII CRLF LRECL(80) RECFM(F)`
4. Press Enter. You should see a message at the top of the screen "File transfer in progress"
5. Press ESC to go to ZTI shell mode
6. Enter command: `upload /path/to/laptop/file.txt`
7. ZTI will upload the file and return you to the TSO READY prompt
8. Repeat from step 3 to upload more files.

## Download Files from PC to Mainframe

1. Log into TSO session
2. Go to READY prompt (exit ISPF)
3. Enter command:  `IND$FILE GET CLEANUP.PROC ASCII CRLF`
4. Press Enter. You should see a message at the top of the screen "File transfer in progress" and a countdown of bytes.    
   Wait until the message disappears.
5. Repeat steps 3 and 4 for as many files as you want to download.
6. Press ESC to go to ZTI shell mode
7. Enter command `downloads` to see a list of pending downloaded files.
8. Enter command `receive /path/to/laptop/file.txt` .  This will bring in the first file from the downloads list. Note 
   that shell expansions like `~` do not work!
9. Repeat steps 7 and 8 for all the available files.
10. Enter command `goto` to return to the TSO READY prompt.
