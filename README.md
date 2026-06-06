# Felicity (Beta)

Felicity (Previously: Face Recognition Photo Organizer) is an offline standalone desktop application for Windows that automatically finds and groups all photos of the same person across your entire photo library. Instead of manually sorting thousands of photos, the app uses artificial intelligence to recognize faces and organize them for you.

A no nonsense photo organiser for windows, if you want to group people by faces without having to deal with complex UI or professional tools. 

- User friendly UI
- No need for manual tagging, or confirming faces
- Completely offline and built for privacy
- Just point to the location of your folders and let the app do its thing.

## Contents
- [Screenshots](#screenshots)
- [Help Documentation](#help)
- [Privacy statement](#privacy-statement)
- [Features](#features)
- [Discussion, Feedback, Reviews, or Showcase](https://github.com/revoconner/Facial-Recognition-Photo-Organiser/discussions/10)
- [Development Tracker](https://github.com/users/revoconner/projects/3)
- [Known bugs](#known-bugs-improvements-and-changelog)
- [License — Source Available](#license-and-usage)

## Screenshots

<img width="auto" height="1530" alt="image" src="https://github.com/user-attachments/assets/62698946-6a84-4127-865f-ac425de2fd99" /></br></br>
<img width="auto" height="1350" alt="image" src="https://github.com/user-attachments/assets/eab36cb1-4595-4719-acaf-ebca777b0db5" /></br></br>

<details>
<summary><h3>More images below (Click to expand)</h3></summary>
<img width="auto" height="690" alt="image" src="https://github.com/user-attachments/assets/b4a487af-8cc9-4527-9de6-c7e8efe5fb96" /></br></br>
<img width="auto" height="681" alt="image" src="https://github.com/user-attachments/assets/a70e8a71-25e7-4a12-aa44-d65d11a81221" /></br></br>
<img width="auto" height="1341" alt="image" src="https://github.com/user-attachments/assets/5588619d-9129-454c-bbfc-97ed724da105" /></br></br>
<img width="auto" height="1518" alt="image" src="https://github.com/user-attachments/assets/4cf0abb6-f87b-4b22-a626-64d846962fb4" /></br></br>
<img width="auto" height="528" alt="image" src="https://github.com/user-attachments/assets/98a8ca26-5d70-438b-9889-e8117478899f" /></br></br>
<img width="auto" height="1332" alt="image" src="https://github.com/user-attachments/assets/02d481ab-4160-4f32-a3af-f89b939e777c" /></br></br>
<img width="auto" height="1509" alt="image" src="https://github.com/user-attachments/assets/77c0f566-0584-4784-af99-8d7a53089d60" /></br></br>
<img width="auto" height="720" alt="image" src="https://github.com/user-attachments/assets/24532caf-b015-4289-8db2-f46141c7a2bd" /></br></br>
<img width="auto" height="336" alt="image" src="https://github.com/user-attachments/assets/8ddf1930-26fd-4595-800a-656b1a1f36ef" /></br></br>
<img width="auto" height="696" alt="image" src="https://github.com/user-attachments/assets/1999eea0-1494-4930-878c-909bfa8534b3" /></br></br>
<img width="auto" height="1269" alt="image" src="https://github.com/user-attachments/assets/a74a3151-2ba0-4214-ac66-d0887db35727" /></br></br>
  
</details>

**Photo Credits:**
- [Blanca Soler](https://www.instagram.com/blanca.soler)
- [Ella Purnell](https://www.instagram.com/ella_purnell)

## Help

For help, see our [Documentation](https://github.com/revoconner/Facial-Recognition-Photo-Organiser/wiki/Help-Documentation)

Remember: The app **never** modifies your original photos, so you can always start fresh if needed by deleting the app data folder and rescanning.

## Privacy statement

<details>
<summary><b>Click to read our privacy statement</b></summary>
The app doesn't connect to the internet in any way or form (unless you specifically specify one of the folder from an online location to be scanned, then it will use the network activity to fetch data from that folder). The app is completely offline, all AI packages and bundles are provided with the setup file. 

You can use this app on an airgapped computer if you want. And as such, we do not collect any data, analytical or otherwise. 

If you plan on reporting a bug, you may have to voluntarily disclose the log file. We will use that log file to track the bug and solve it for next patch, and as such the log file may be available on the open web for an indefinite amount of time.  The log file, while not containing any identifier, will be associated with the account that submits the bug report. Use an alternate account if you want your account to not be associated with the log file. 
</details>

## Features
- User friendly GUI, built by professional for everyday users!
- Hide people from list
- Rename people
- Hide photos
- Preview photos or open them in your default photos app
- Hide people with less than X photos
- Change thumbnail for people's list
- Sort by name of number of photos
- Quickly jump to a person
- Transfer face tag to another person to remove it (for false positive; in my testing with 90,980 real everyday photos, false positives were a rarity)
- Hide unnamed people
- Auto naming conflict resolution
- Finds new photos or deleted photos on disk autmatically
- Exclusion by wildcard or subfolder
- Doesn't change your folder structure, the faces only work inside the app and is kept in a separate database. So if you have organised your folders in a certain way, it won't mess with that.
- Lets user decide the threshold percentage, for facial matching (45%-50% recommended)
- Allocates system resources dynamically so as not to bog down your system.

### Comparison with other photo management software

Our focus is on creating a user friendly app to organise photos by person instead of creating an app that does everything photo related, making them cluttered. This keeps the UI easy and clean to be user friendly to everyone, not just professionals. 

<details>
<summary><b>Expand comparison table</b></summary>
<table>
  <thead>
    <tr>
      <th>Feature</th>
      <th>FRPO</th>
      <th>DigiKam</th>
      <th>Tonfotos</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td><strong>UI Complexity</strong></td>
      <td>Easy</td>
      <td>Hard</td>
      <td>Medium</td>
    </tr>
    <tr>
      <td><strong>Manual Tagging Not Required</strong></td>
      <td>✓ (Very Accurate)</td>
      <td>✗ (Accuracy drops with large amount of photos)</td>
      <td>✗ (Cleanup required from time to time)</td>
    </tr>
    <tr>
      <td><strong>Photo Management Library</strong></td>
      <td>Only for organising by faces</td>
      <td>Full suite (editing, GPS, collections, batch processing, metadata)</td>
      <td>Timeline, albums, smart filters, events</td>
    </tr>
    <tr>
      <td><strong>Instant Re-clustering (no rescan)</strong></td>
      <td>✓</td>
      <td>✗</td>
      <td>✗</td>
    </tr>
    <tr>
      <td><strong>Tag Preservation Across Re-clustering</strong></td>
      <td>✓</td>
      <td>✗</td>
      <td>✗</td>
    </tr>
    <tr>
      <td><strong>Dedicated Unmatched Faces Group</strong></td>
      <td>✓</td>
      <td>✗</td>
      <td>✗</td>
    </tr>
    <tr>
      <td><strong>Dynamic CPU Throttling (background)</strong></td>
      <td>✓</td>
      <td>✗</td>
      <td>✗</td>
    </tr>
    <tr>
      <td><strong>Scan Frequency Options</strong></td>
      <td>✓ (4 modes)</td>
      <td>✗ (manual only)</td>
      <td>✗ (auto only)</td>
    </tr>
    <tr>
      <td><strong>InsightFace 99.8% Accuracy</strong></td>
      <td>✓</td>
      <td>✗ (~95%)</td>
      <td>✗ (~98%)</td>
    </tr>
    <tr>
      <td><strong>Manual Face Transfer Between Persons</strong></td>
      <td>✓</td>
      <td>Limited</td>
      <td>✓</td>
    </tr>
    <tr>
      <td><strong>Primary Photo Selection per Person</strong></td>
      <td>✓</td>
      <td>✗</td>
      <td>✓</td>
    </tr>
    <tr>
      <td><strong>View Mode: Zoom to Tagged Faces</strong></td>
      <td>✓</td>
      <td>✗</td>
      <td>✓</td>
    </tr>
    <tr>
      <td><strong>Cost</strong></td>
      <td>Free - Non Commercial</td>
      <td>Free</td>
      <td>✗ ($99)</td>
    </tr>
    <tr>
      <td><strong>Photo Editing</strong></td>
      <td>✗</td>
      <td>✓</td>
      <td>✓</td>
    </tr>
    <tr>
      <td><strong>Timeline View</strong></td>
      <td>✗</td>
      <td>✓</td>
      <td>✓</td>
    </tr>
    <tr>
      <td><strong>Duplicate Detection</strong></td>
      <td>TBA - Planned Feature</td>
      <td>✓</td>
      <td>✓</td>
    </tr>
    <tr>
      <td><strong>Metadata Management</strong></td>
      <td>TBA - Planned Feature</td>
      <td>✓</td>
      <td>Limited</td>
    </tr>
    <tr>
      <td><strong>Cross-Platform</strong></td>
      <td>✗ (Windows only)</td>
      <td>✓ (Linux/Win/Mac)</td>
      <td>✗ (Windows only)</td>
    </tr>
    <tr>
      <td><strong>Photo Enhancement/Filters</strong></td>
      <td>✗</td>
      <td>✓</td>
      <td>✓</td>
    </tr>
  </tbody>
</table>
</details>

## Known Bugs, improvements and changelog:
- [Changelog](https://github.com/revoconner/Facial-Recognition-Photo-Organiser/releases)
- [Bug tracker and Features](https://github.com/revoconner/Facial-Recognition-Photo-Organiser/issues?q=sort%3Aupdated-desc+is%3Aissue+is%3Aopen)


----

## License and Usage — Source Available (Not Open Source)

This software and code is provided as is, free of cost, for personal and commercial use, provided you do not redistribute the code, or packaged software for commercial use. Read [License](LICENSE).

----

## LLM generated code notice
#### Some parts of the source code is LLM generated, here's a summary of it:
- Variable names in part have been changed to be more accurate to represent what they do.
- Explanatory comments for defs, func and class have been converted to be nore readable and user source friendly in case someone forks it.
- This README.md file has been originally written by Sonnet 4, but later revised by me.
