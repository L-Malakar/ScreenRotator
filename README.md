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
```dash
git clone [https://github.com/L-Malakar/ScreenRotator.git](https://github.com/L-Malakar/ScreenRotator.git)
```
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
