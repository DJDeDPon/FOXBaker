# FOXBaker

This app created for bake-sub-to-video. It provides a simple graphical user interface to hardcode (or "burn") an `.ass` or `.srt` subtitle file into a video.

## Prerequisites

Before you begin, ensure you have the following installed and configured on your system.

**Python**

You will need Python 3.8 or newer.

**FFmpeg**

This application depends on FFmpeg to perform all video processing.

1.  Download FFmpeg from the official website: [ffmpeg.org](https://ffmpeg.org/download.html)
2.  Unzip the downloaded file to a location on your computer (for example, `C:\ffmpeg`).
3.  You must add the `bin` folder from within the FFmpeg directory (e.g., `C:\ffmpeg\bin`) to your system's PATH environment variable. This is a critical step that allows the application to execute FFmpeg commands.

A guide on how to add a folder to your PATH on Windows can be found [here](https://www.architectryan.com/2018/03/17/add-to-the-path-on-windows-10/).

## Installation

1.  Clone the repository to your local machine:
    ```bash
    git clone [https://github.com/DJDeDPon/FOXBaker.git](https://github.com/your-username/FOXBaker.git)
    cd FOXBaker
    ```

2.  Install the required Python packages using pip:
    ```bash
    pip install -r requirements.txt
    ```

## Usage

1.  Run the application from the project directory:
    ```bash
    python main.py
    ```

2.  Use the interface to select your source video file and subtitle file.
3.  Choose the desired output name, location, and quality settings.
4.  Click "Start Render" to begin the process.