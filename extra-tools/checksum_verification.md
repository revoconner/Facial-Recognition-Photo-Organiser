## SHA-256 result:

PhotosOrganise.exe: 8F0E3B0B697B26CA74F6A5A3CB74528A166191E9328892C8B0F124AE63720C82
PhotoExporter.exe : 402D821D9F73ADC629D08D6F02564432F4E929AA40296D85AF3318E43B85A254
organise.cpp      : E599EDE267BA8F519042E7E552919EA4D6A77F0F517FBB01A9102D96204FECD8
extract.cpp       : 78A72268B6C9F55E543E0E265F685678AA46C064FA8E35AC13DB8C402A37E115


## What is this? 

This file contains the verification hash for all the binary and source code files provided, and lets user verify the legitimacy of the binaries before executing them.
If you don't understand what it is, do not worry, it doesnt really do anything other than let people verify (if they want to) that the files are legitimate and haven't been tampered by a malware. 


If you wanna learn more about checksum verification, read below




#### What is a Hash?

A hash is like a unique digital fingerprint for a file. When you run a file through a hash algorithm (like SHA-256), it generates a long string of letters and numbers. Even the tiniest change to the file - a single bit - will produce a completely different hash.

#### Why Does This Matter?
When you download software from the internet, you want to make sure:

- The file wasn't corrupted during download
- No one has tampered with it or injected malware
- You're getting exactly what the creator intended.

#### How to Verify

Windows (PowerShell): Run the command in a powershell terminal, replace PhotosOrganise.exe with the name of the file you want to check.

```powershell
Get-FileHash PhotosOrganise.exe -Algorithm SHA256

```

Compare the output with the hash provided above. If they match exactly, the file is legitimate and unmodified. If even one character is different, something is wrong - don't run the file.

#### Real World Analogy

Think of it like a wax seal on a letter. If the seal is intact and matches the sender's mark, you know the letter wasn't opened or tampered with during transit. 

Hash verification does the same thing for digital files.