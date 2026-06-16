#!/usr/bin/env python3
# ↑ Lets you run this script directly on Unix/macOS (optional convenience).

import os          # Provides filesystem operations (paths, walking directories)
import sys         # Allows program exit and command-line interaction
import shutil      # Used to check if an external command (ebook-convert) exists
import subprocess  # Lets us run external programs like Calibre’s ebook-convert

# === CONFIGURATION SECTION ===

# The root folder containing all your EPUBs and subfolders.
ROOT_DIR = "/Users/as/Library/CloudStorage/GoogleDrive-andreas.seel86@gmail.com/My Drive/ebooks"

# Whether to overwrite existing PDFs (True = overwrite, False = skip)
OVERWRITE = False

# If True, the script will *not* actually convert anything — it just lists what it would do.
DRY_RUN = False

# === END CONFIGURATION ===


def main():
    """
    Main function — walks through all folders under ROOT_DIR,
    finds .epub files, and converts them to .pdf using Calibre.
    """

    # --- Check for Calibre's 'ebook-convert' command availability ---
    if not shutil.which("ebook-convert"):
        # If Calibre CLI isn’t installed, show instructions and exit.
        print("❌ 'ebook-convert' not found.")
        print("Install Calibre CLI on macOS:\n  brew install --cask calibre\n"
              "Then run:\n  /Applications/calibre.app/Contents/MacOS/calibre_postinstall")
        sys.exit(1)

    # Counters for summary statistics
    total_found = 0       # Number of EPUBs found in all subfolders
    total_skipped = 0     # Number of EPUBs skipped because PDFs already exist
    total_converted = 0   # Number of EPUBs successfully converted
    errors = []           # List to collect any conversion errors

    # --- Walk through all folders and subfolders ---
    for dirpath, dirnames, filenames in os.walk(ROOT_DIR):
        # dirpath: current directory path
        # dirnames: list of subdirectories (not used here)
        # filenames: list of files in this directory

        # Loop through each file in the current folder
        for name in filenames:
            # Check if file ends with ".epub" (case-insensitive)
            if name.lower().endswith(".epub"):
                total_found += 1  # Increment found counter

                # Full absolute path to the EPUB file
                epub_path = os.path.join(dirpath, name)

                # The output PDF will have the same name but ".pdf" extension
                pdf_path = os.path.splitext(epub_path)[0] + ".pdf"

                # If we don't want to overwrite and the PDF already exists → skip it
                if not OVERWRITE and os.path.exists(pdf_path):
                    print(f"⏭️  Skipping (exists): {pdf_path}")
                    total_skipped += 1
                    continue  # Move on to the next file

                # Print a relative path for easier reading in logs
                print(f"🔁 Converting: {os.path.relpath(epub_path, ROOT_DIR)}")

                # If in "dry run" mode, don’t actually run the conversion
                if DRY_RUN:
                    total_converted += 1
                    continue

                # --- Perform the actual conversion using Calibre ---
                try:
                    # Build the command line: ebook-convert "input.epub" "output.pdf"
                    # You can add extra options after pdf_path (e.g., "--paper-size", "--disable-font-rescaling", etc.)
                    cmd = ["ebook-convert", epub_path, pdf_path]

                    # Run the command, raising an error if it fails
                    subprocess.run(cmd, check=True)

                    # If successful, increment counter and print confirmation
                    total_converted += 1
                    print(f"✅ Wrote: {os.path.relpath(pdf_path, ROOT_DIR)}")

                except subprocess.CalledProcessError as e:
                    # If conversion fails, record the error and continue with the next file
                    msg = f"❌ Failed: {epub_path} ({e})"
                    print(msg)
                    errors.append(msg)

    # --- Print a nice summary of what happened ---
    print("\n—— Summary ——")
    print(f"EPUBs found:      {total_found}")
    print(f"Converted:        {total_converted}{' (dry run)' if DRY_RUN else ''}")
    print(f"Skipped (exists): {total_skipped}")

    # If any errors occurred, show how many and a few examples
    if errors:
        print(f"Errors:           {len(errors)}")
        for m in errors[:5]:  # Show first 5 errors only
            print(" •", m)
        if len(errors) > 5:
            print(f" • …and {len(errors)-5} more")

# --- Standard Python boilerplate ---
# Ensures that main() only runs when this file is executed directly,
# not when it’s imported as a module in another script.
if __name__ == "__main__":
    main()