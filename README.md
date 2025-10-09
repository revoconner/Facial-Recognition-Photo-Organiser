# Organise Photos by Faces (Beta)

Face Recognition Photo Organizer is a desktop application for Windows that automatically finds and groups all photos of the same person across your entire photo library. Instead of manually sorting thousands of photos, the app uses artificial intelligence to recognize faces and organize them for you.

A no nonsense photo organiser for windows, if you want to group people by faces without having to deal with complex UI or professional tools. With negligible false results, the cutting edge AI backed program scans your folder and groups users users together by faces. </br>

No more manual tagging, no more confirming for weighted algorithm. Just scan and wait for the results. Responsive UI, user friendly settings with tooltips explaining everything, including filtering out unwanted locations, wildcards for advanced users and hding people in multiple ways. The software is in beta at the moment, and is being personally being used by me to sort through hundreds of thousands of photos all taken as back as 2010, and organise them. So they are already being tested in real time with a huge database. 

## Screenshots
<img width="auto" height="1530" alt="image" src="https://github.com/user-attachments/assets/a2782e8d-8f3a-49b6-a868-963ebf481f21" /></br></br>
<img width="auto" height="1350" alt="image" src="https://github.com/user-attachments/assets/77c0f566-0584-4784-af99-8d7a53089d60" /></br></br>

<details>
<summary><b>More images below (Click to expand)</b></summary>
<img width="auto" height="690" alt="image" src="https://github.com/user-attachments/assets/b4a487af-8cc9-4527-9de6-c7e8efe5fb96" /></br></br>
<img width="auto" height="681" alt="image" src="https://github.com/user-attachments/assets/a70e8a71-25e7-4a12-aa44-d65d11a81221" /></br></br>
<img width="auto" height="1341" alt="image" src="https://github.com/user-attachments/assets/5588619d-9129-454c-bbfc-97ed724da105" /></br></br>
<img width="auto" height="1518" alt="image" src="https://github.com/user-attachments/assets/4cf0abb6-f87b-4b22-a626-64d846962fb4" /></br></br>
<img width="auto" height="528" alt="image" src="https://github.com/user-attachments/assets/98a8ca26-5d70-438b-9889-e8117478899f" /></br></br>
<img width="auto" height="1332" alt="image" src="https://github.com/user-attachments/assets/02d481ab-4160-4f32-a3af-f89b939e777c" /></br></br>
<img width="auto" height="1509" alt="image" src="https://github.com/user-attachments/assets/eab36cb1-4595-4719-acaf-ebca777b0db5" /></br></br>
<img width="auto" height="720" alt="image" src="https://github.com/user-attachments/assets/24532caf-b015-4289-8db2-f46141c7a2bd" /></br></br>
<img width="auto" height="336" alt="image" src="https://github.com/user-attachments/assets/8ddf1930-26fd-4595-800a-656b1a1f36ef" /></br></br>
<img width="auto" height="696" alt="image" src="https://github.com/user-attachments/assets/1999eea0-1494-4930-878c-909bfa8534b3" /></br></br>
<img width="auto" height="1269" alt="image" src="https://github.com/user-attachments/assets/a74a3151-2ba0-4214-ac66-d0887db35727" /></br></br>
  
</details>

## Table of content
- [Features](#features)
- [Comparison with other similar apps](#comparison-with-other-photo-management-software)
- [Known bugs](#known-bugs-improvements-and-changelog)
- [User Guide](#user-guide)
- [License and Usage](#license-and-usage)
- [Performance Figures](pPerformance-stats)




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

## Comparison with other photo management software

Our focus is on creating a user friendly app to organise photos by person instead of creating an app that does everything photo related, making them cluttered. This keeps the UI easy and clean to be user friendly to everyone, not just professionals. 

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
      <td>Free</td>
      <td>Free</td>
      <td>✗ ($99)</td>
    </tr>
    <tr>
      <td><strong>Single Executable Size</strong></td>
      <td>✓ (minimal)</td>
      <td>✗ (heavy KDE)</td>
      <td>✓</td>
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
      <td>✗</td>
      <td>✓</td>
      <td>✓</td>
    </tr>
    <tr>
      <td><strong>Metadata Management</strong></td>
      <td>✗</td>
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

## Known Bugs, improvements and changelog:
[These are detailed in the release versions](https://github.com/revoconner/Facial-Recognition-Photo-Organiser/releases)

----


# User Guide

<details><summary><b>Click here to expand the user guide</b></summary>
## Table of content

- [What Is This App?](#what-is-this-app)
- [How It Works](#how-it-works)
- [Getting Started](#getting-started)
  - [First Launch](#first-launch)
  - [Adding Photo Folders](#adding-photo-folders)
- [Understanding the Interface](#understanding-the-interface)
  - [Main Window Layout](#main-window-layout)
  - [Top Controls](#top-controls)
- [Working with People](#working-with-people)
  - [Viewing Someone's Photos](#viewing-someones-photos)
  - [Renaming a Person](#renaming-a-person)
  - [Setting a Primary Photo](#setting-a-primary-photo)
  - [Hiding a Person](#hiding-a-person)
  - [Hiding Individual Photos](#hiding-individual-photos)
  - [Remove/Transfer Tag](#removetransfer-tag)
- [Settings Explained](#settings-explained)
  - [General Settings](#general-settings)
  - [Folders to Scan](#folders-to-scan)
  - [View Log](#view-log)
- [Tips and Best Practices](#tips-and-best-practices)
  - [Getting the Best Results](#getting-the-best-results)
  - [Working with Large Photo Collections](#working-with-large-photo-collections)
  - [Adding New Photos](#adding-new-photos)
- [Keyboard Shortcuts](#keyboard-shortcuts)
- [Common Questions](#common-questions)
- [Troubleshooting](#troubleshooting)
- [Advanced Features](#advanced-features)
  - [Development Options](#development-options)
- [License and Usage](#license-and-usage)
- [Version Information](#version-information)
- [Getting Help](#getting-help)

## What Is This App?

Face Recognition Photo Organizer is a desktop application for Windows that automatically finds and groups all photos of the same person across your entire photo library. Instead of manually sorting thousands of photos, the app uses artificial intelligence to recognize faces and organize them for you.

## How It Works

The app works in two simple steps:

1. **Scan Your Photos** - The app looks through your photo folders once to find all faces
2. **Group Similar Faces** - Faces that look alike are automatically grouped together as the same person

Once scanning is complete, you can instantly adjust how strict the matching is without rescanning everything.

## Getting Started

### First Launch

When you first open the app, you will see a message that says "No Folders to Scan". This is normal because you need to tell the app where your photos are located.

Click the "Take me to settings" button to add your photo folders.

### Adding Photo Folders

1. Click the **Settings** button at the bottom of the screen
2. Go to the **Folders to Scan** tab
3. Under "Include folders for scanning", click the **+ Add Folder** button
4. Select the folder containing your photos
5. Repeat for any additional photo folders you have
6. Close Settings

The app will now automatically start scanning your photos. This initial scan can take some time depending on how many photos you have.

## Understanding the Interface

### Main Window Layout

The app window has four main sections:

**Left Panel - People List**
- Shows all the people detected in your photos
- Each person is labeled "Person 1", "Person 2", etc. until you rename them
- Shows how many photos contain each person
- Click on a person to see their photos

**Right Panel - Photo Grid**
- Displays thumbnail previews of photos for the selected person
- Single-click a photo to preview it in a larger view inside the app
- Double-click a photo to open it in your default image viewer
- Use the size slider at the top to make thumbnails bigger or smaller

**Bottom Progress Bar**
- Shows scanning progress when processing photos
- Displays status messages

**Bottom Status Bar**
- Shows technical information like GPU status
- Displays total number of faces found
- Help button on the right for quick tips

### Top Controls

**View Mode Dropdown**
- **Show entire photo** (default) - Thumbnails show the full image
- **Zoom to tagged faces** - Thumbnails zoom into just the person's face, helpful for identifying people in group photos

**Size Slider**
- Adjust how large or small the photo thumbnails appear

**Filter Button (three horizontal lines)**
- Sort people by name (A to Z or Z to A)
- Sort people by number of photos (low to high or high to low)

**Jump To Button (grid of dots)**
- Only appears when sorting by name
- Click to see an alphabet list
- Click a letter to quickly jump to names starting with that letter

## Working with People

### Viewing Someone's Photos

1. Click on a person's name in the left panel
2. All photos containing that person appear in the right panel
3. Use the photo preview to browse through their photos

### Renaming a Person

By default, people are named "Person 1", "Person 2", etc. You should rename them to actual names:

1. Find the person in the left panel
2. Click the three-dot menu next to their name
3. Select **Rename**
4. Type the person's real name
5. Click **Confirm**

All photos of that person are now tagged with their name. This name will persist even if you adjust settings or add new photos later.

### Setting a Primary Photo

The first photo shown for each person is their "primary photo". You can change this:

1. View the person's photos in the right panel
2. Find the photo you want to use as their primary photo
3. Click the three-dot menu on that photo
4. Select **Make primary photo**

The person's avatar in the left panel will now use this photo.

### Hiding a Person

If someone appears in your photos but you don't want them in the list:

1. Click the three-dot menu next to their name
2. Select **Hide person**

They will disappear from the list. To see them again, turn on "Show hidden person" in Settings.

### Hiding Individual Photos

To hide specific photos without hiding the entire person:

1. Click the three-dot menu on the photo
2. Select **Hide photo**

Hidden photos appear with diagonal lines when "Show hidden photos" is enabled in Settings.

### Remove/Transfer Tag

1. Click the three-dot menu on the photo
2. Click on either remove tag. This will permanently hide the photo (later releases will mvoe it to unmatched faces) OR
3. Click on one of the names from person list (only people you have renamed will appear here), the photo will now be a part of their grid. 

## Settings Explained

Click the **Settings** button at the bottom left to access all settings.

### General Settings

**Threshold**
- Controls how similar two faces need to be to match
- Lower values (30-40%) - More lenient, may group different people together
- Higher values (50-60%) - More strict, may split the same person into multiple entries
- Default: 50%
- After changing, click **Recalibrate** to regroup all faces
- Start at 45% - 50% and adjust based on your results

**Use system resources dynamically**
- When ON: App slows down when minimized to tray to save computer resources
- When OFF: App runs at full speed always
- Default: ON
- NOTE: You must use close to tray to use this

**Show single unmatched images**
- When ON: Shows a group called "Unmatched Faces" containing people who appear only once
- These are usually screenshots, memes, or random images you don't care about
- When OFF: Hides these single-appearance faces
- Default: OFF

**Hide persons with less than X photos**
- When enabled, people with fewer than the specified number of photos are hidden
- Useful for filtering out people who only appear once or twice
- Default: OFF (set to 2 photos when enabled)

**Close to tray**
- When ON: Clicking X minimizes the app to your system tray instead of closing it
- To fully quit, right-click the tray icon and select Quit
- Default: ON

**Show hidden person**
- When ON: People you previously hid appear in the list again with "(hidden)" in their name
- You can unhide them individually from their menu
- Default: OFF

**Show hidden photos**
- When ON: Photos you hid appear with diagonal lines across them
- You can unhide them individually from their menu
- Default: OFF

**Show development options**
- Shows technical statistics like how many faces are tagged
- Regular users should keep this off
- Default: OFF

### Folders to Scan

**Include folders for scanning**
- Add all folders containing photos you want to organize
- The app scans these folders and all subfolders
- Supported formats: JPG, JPEG, PNG, BMP, GIF, HEIC, HEIF

**Exclude subfolders from scanning**
- Add specific subfolders you want to skip
- These are NOT scanned even if they are inside an included folder
- Takes priority over included folders

**Wildcard Exclusion**
- Use patterns to exclude files or folders
- Examples:
  - `*.gif` - Skip all GIF files
  - `*thumbnail` - Skip folders with "thumbnail" in the name
  - `*cache*` - Skip folders containing "cache"
- Separate multiple patterns with commas

**Rescan For Changes**
- Manually trigger a new scan
- Use this when you have added or deleted photos
- The app will find new photos and remove deleted ones from the database

### View Log

The log shows all actions the app has taken, including:
- When scanning started and finished
- How many photos were found
- Any errors that occurred
- Settings changes you made

Click **Save Log** to save the log as a text file for troubleshooting.

## Tips and Best Practices

### Getting the Best Results

**Start with Default Settings**
- Use the 50% threshold initially
- Scan your photos and review the results
- Adjust threshold up or down based on what you see

**Adjust Threshold Based on Results**
- Too many different people grouped together? Raise the threshold
- Same person split into multiple entries? Lower the threshold

**Name People as You Go**
- Once someone is named, the app remembers them forever
- New photos of that person will automatically appear under their name
- Named people are easier to find and organize

**Use Hidden Features Wisely**
- Hide unmatched faces to focus on real people
- Hide persons with fewer than 2-3 photos to reduce clutter
- Only show hidden items when you need to review them

### Working with Large Photo Collections

**Be Patient During First Scan**
- The initial scan takes time but only happens once
- You can minimize the app to the tray to reduce system impact
- The app will continue working in the background

**Use Dynamic Resources**
- Keep this setting ON if you use your computer while scanning
- The app will slow down when minimized so it doesn't interfere with your work

**Organize in Stages**
- Name your most important people first
- Use the photo count sorting to find people who appear most often
- Work through the list gradually

### Adding New Photos

When you add new photos to your folders:
1. Open the app
2. Go to Settings > Folders to Scan
3. Click **Rescan For Changes**

The app will find new photos and automatically add them to the correct people if they are already named.

## Keyboard Shortcuts

**In Photo Preview (Lightbox)**
- Left Arrow - Previous photo
- Right Arrow - Next photo
- Escape - Close preview

## Common Questions

**Why is Person 1 labeled "Unmatched Faces"?**
This is a special group containing faces that don't match anyone else. These are typically screenshots, memes, profile pictures, or people who appear only once. You can hide this group in Settings.

**Will the app modify my original photos?**
No. The app only reads your photos. It never edits, moves, or deletes the original image files. All organization happens in the app's database.

**What happens if I delete photos from my computer?**
The next time you rescan, the app will remove those photos from its database automatically.

**Can I use this on multiple computers?**
The app stores its data in your user profile. Each computer has its own separate database. You would need to scan and organize photos separately on each computer.

**Where is my data stored?**
All data is stored in: `C:\Users\[YourUsername]\AppData\Roaming\facial_recognition\face_data` or for sort `%appdata%\facial_recognition\face_data`

This includes the photo database and face recognition data. Your original photos remain in their original locations.

**Why does the app use so much GPU/CPU?**
Face recognition is computationally intensive. The app uses your graphics card (GPU) if available for faster processing. Enable "Use system resources dynamically" to reduce impact when the app is minimized.

**Can I back up my data?**
Yes. Back up the folder mentioned above to preserve all your people names and organization. Restore this folder to recover your data.

## Troubleshooting

**App takes a long time to start**
- It's a known bug for the time the app starts. Consecutive starts should be shorter.

**Stuck at loading photos**
- If the number of photos is huge (say 3000) the load time for the first try might take a little bit as the system builds cache.
- Marked for improvement
  
**App won't start scanning**
- Make sure you have added at least one folder in Settings > Folders to Scan
- Check that the folder path is correct and accessible
- Try clicking "Rescan For Changes"

**No faces detected in my photos**
- Make sure your photos actually contain visible faces
- Check that the photos are in a supported format (JPG, PNG, HEIC, etc.)
- Very small or blurry faces may not be detected

**Same person appears as multiple different people**
- Increase the threshold value in Settings > General Settings
- Click Recalibrate after changing the threshold
- Try values between 50-60%

**Different people grouped together**
- Decrease the threshold value
- Click Recalibrate
- Try values between 30-40%

**App is slow or freezing**
- Enable "Use system resources dynamically"
- Minimize the app to tray while scanning
- Close other heavy applications
- The first scan is the slowest; subsequent operations are much faster

**Photos not opening in default viewer**
- Make sure you have a default app set for image files
- Try right-clicking a photo file in Windows Explorer and selecting "Open with" to set a default app

**Names disappeared after recalibration**
- This should not happen. If it does, report it as a bug
- Names are tied to individual faces and should persist through all operations

**Thumbnails are rendering weirdly, or not matching the face**
- Clear cache in settings.
- Next time you open a person's grid, the thumbnail cache will automatically be built in the background.
- Person with large number of photos might take some time to load the first time the cache is being built.

## Advanced Features

### Development Options

When "Show development options" is enabled in Settings, you will see additional information:

**Tag Statistics**
- Shows how many faces are tagged vs total faces for each person
- Format: "Person Name (45/50 tagged)"
- Helps you understand confidence in person identification

**Remove All Tags**
- Accessible from the person's menu
- Removes all name tags, reverting person back to "Person X"
- Use this if you want to start fresh with naming
</details>


----

## License and Usage

This app is provided free of cost, and no usage restriction for personal, non-commercial use only. You may not use this app on computers used for commercial purposes, even if the app itself is being used for personal use.

We do not collect any of your data, this app does not send any data online and works completely offline. If you see any network activity on this app, report a bug immediately with the details. 

The app uses facial recognition technology. You are responsible for complying with applicable privacy laws and obtaining consent from individuals whose images are processed.


## Performance Stats
1. [10/7/2025, 5:46:28 AM] - [10/7/2025, 10:50:24 AM] - Scan complete: 104577 faces in 90491 photos
2. Took almost 5 hours to scan 90,000 photos for 100,000 faces from a Seagate Exos HDD, running on AMD Threadripper 7960x
3. [10/7/2025, 10:46:38 AM] - [10/7/2025, 10:50:24 AM] - Custering to person identification
4. Took 4 minutes on Nvidia RTX 4090 for face clustering and identification

## Getting Help

If you encounter issues not covered in this guide:
1. Check the log in Settings > View Log for error messages
2. Save the log file for reference
3. Make sure you are using the latest version of the app

Remember: The app **never** modifies your original photos, so you can always start fresh if needed by deleting the app data folder and rescanning.
