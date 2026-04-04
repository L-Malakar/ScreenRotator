# ScreenRotator Auto 🔴

![License](https://img.shields.io/badge/license-MIT-green)
![Python](https://img.shields.io/badge/python-3.8%2B-blue)
![Platform](https://img.shields.io/badge/platform-Windows-lightgrey)

**ScreenRotator Auto** is a professional-grade, open-source Windows utility providing a seamless way to manage display orientation via global keyboard macros. Developed by **L. Malakar**, this tool is designed for users who require instant screen adjustments without navigating deep system menus.

---

## 🛠️ Installation & Build

### 1. Prerequisites
* **OS:** Windows 10 or 11.
* **Python:** [Python 3.8 or higher](https://www.python.org/downloads/).
* **Privileges:** **Administrator access** is required for the application to hook global hotkeys and rotate the display.

### 2. Environment Setup

Follow these steps to download the source code and prepare your system to run or modify the application:

**Step 1: Install Git (If not already installed)**
You need Git to clone the repository. If you don't have it, download and install it from [git-scm.com](https://git-scm.com/).

**Step 2: Open Terminal or Command Prompt**
Press `Win + R`, type `cmd`, and hit Enter. Alternatively, right-click in your desired project folder and select "Open Git Bash here."

**Step 3: Clone the Repository**
Copy and paste the following command to download the project files:
```
git clone [https://github.com/L-Malakar/ScreenRotator.git](https://github.com/L-Malakar/ScreenRotator.git)
```

**Step 4: Navigate to the Project Folder**
Move your terminal into the newly created directory:

```
cd ScreenRotator
```

**Step 5: Install Required Libraries**
Run this command to install the Python modules needed for the UI and screen rotation:

```
pip install rotatescreen keyboard pystray Pillow pywin32 winshell
```

**Step 6: Verify Assets**
Ensure logo.ico and rotate pc.py are in the same folder. These were included when you ran the git clone command.

**Step 7: Build the Standalone Executable**
Now you can run the build command. Since you mentioned the .ico is already in your repo, this command will work perfectly:

```
python -m PyInstaller --noconsole --onefile --uac-admin --icon="logo.ico" --add-data "logo.ico;." --name "ScreenRotator" "rotate pc.py"
```

---

### 📂 Locating Your Executable (.exe)

Once the PyInstaller command finishes, you will notice several new folders in your project directory (`build`, `dist`, and a `.spec` file). 

**How to find your app:**
1. Open the folder named **`dist`**.
2. Inside, you will find a single file named **`ScreenRotator.exe`**.
3. **Move or Run:** You can now move this `.exe` anywhere (like your Desktop). Because we used the `--onefile` and `--add-data` flags, it contains all the icons and logic inside that one file.

**Note on Clean-up:**
After the build is successful, you can safely delete the `build` folder and the `ScreenRotator.spec` file. They are only temporary files used during the compilation process.

---

### 📂 Project Structure After Build
Your folder will look like this:
* 📁 **dist/** <-- **(Your finished .exe is here!)**
* 📁 **build/** (Temporary files, can be deleted)
* 📄 **rotate pc.py** (Your source code)
* 📄 **ScreenRotator.spec** (Build configuration, can be deleted)
* 🖼️ **logo.ico** (Your original assets)

---

## ✨ Key Features

* **Global Hotkeys:** Rotate your screen instantly from any application using custom-defined keyboard shortcuts.
* **Verified Orientation Mapping:**
    * **Up:** Landscape (0°)
    * **Right:** Portrait (90° CW)
    * **Down:** Landscape Flipped (180°)
    * **Left:** Portrait Flipped (270° CW)
* **Deferred Save Logic:** Changes to hotkeys are held in a "pending" state and only take effect once you click **Save Changes**, preventing accidental system lockouts or crashes.
* **Stability & Thread-Safety:** Utilizes a mutex-locking mechanism during hotkey registration to ensure the application remains stable during real-time updates.
* **Persistent Branding:** Custom `logo.ico` integration across every window level, including Taskbar, Alt+Tab menu, and child dialogs.
* **Startup Integration:** Easily add the application to Windows Startup via elevated scheduled tasks directly from the settings menu.

---

## 📖 How to Use

1. **Launch:** Run the application. A 🔴 icon will appear in your system tray.
2. **Rotate:** Use the default `Ctrl + Alt + [Arrow Key]` combinations to change orientation.
3. **Settings:** Right-click the tray icon to:
    * Customize hotkey combinations.
    * Set maximum key limits.
    * Toggle Windows Startup options.
4. **Safety Guard:** If you modify settings but try to close the window without saving, the app will warn you that "Changes are not saved."

---

## 🤝 Contributing
Contributions are welcome! If you find a bug or have a suggestion for the rendering logic, please open an issue or submit a pull request.

**Developed by:** [L. Malakar](https://github.com/L-Malakar/)  
**Release Year:** 2026
