# Automated Screenshot Renaming Tool

This is a Python script designed to solve a real-world automation problem: automatically renaming a large batch of screenshot files based on content found within the images themselves. This tool was built to streamline the process of archiving daily screenshots from a trading platform.

## The Problem

Manually renaming dozens or hundreds of screenshots every day is a time-consuming and error-prone task. The core challenge was that the key piece of information (the time) appeared at a different location in every screenshot, making simple automation impossible. Furthermore, the OCR (Optical Character Recognition) was often confused by other numbers on the screen, like the time on the Windows Taskbar or the time-axis of the chart.

## The Solution

This script implements a robust, multi-step strategy to achieve pure automation:

1.  **Aggressive Cropping:** The script first programmatically crops the top and bottom sections of each screenshot. This intelligently removes all "noise" like browser tabs and the taskbar, forcing the OCR to focus only on the main chart area.
2.  **Powerful OCR Engine:** It utilizes the **EasyOCR** library, a deep learning-based OCR engine, for its superior accuracy in reading text from complex images like software user interfaces.
3.  **Intelligent Parsing:** The script searches the clean OCR output for the first text block that matches a time-like pattern (e.g., HH:MM, HH.MM, or HH;MM).
4.  **Automated Renaming:** Finally, it uses this extracted time, along with user-provided details (Date, Company, Strike Price), to rename the file into a consistent, organized format.

## Skills Demonstrated

This project showcases the following key skills:

-   **Problem Solving & Debugging:** Iteratively diagnosed and solved multiple points of failure, from incorrect OCR readings to fundamental strategy flaws.
-   **Python Scripting:** Wrote a clean, reusable Python script to handle file system operations and process images.
-   **Computer Vision & OCR:** Successfully implemented and configured the EasyOCR library to extract specific data from images.
-   **Process Automation:** Created a tool that transforms a tedious manual workflow into a fully automated, "one-click" solution.
