#!/usr/bin/env python3
import os
import sys
import argparse

def get_relative_files(base_dir):
    base_dir = os.path.abspath(base_dir)
    files = set()
    print(f"Scanning {base_dir}...", file=sys.stderr, flush=True)
    count = 0
    try:
        for root, dirs, filenames in os.walk(base_dir):
            # Calculate relative path from base_dir
            rel_root = os.path.relpath(root, base_dir)
            if rel_root == ".":
                rel_root = ""
            for filename in filenames:
                rel_path = os.path.join(rel_root, filename)
                files.add(rel_path)
                count += 1
                if count % 500 == 0:
                    print(f"  Found {count} files so far...", file=sys.stderr, end="\r", flush=True)
    except KeyboardInterrupt:
        print("\nScan interrupted by user.", file=sys.stderr, flush=True)
        sys.exit(1)
    
    print(f"\n  Done. Found {count} files.", file=sys.stderr, flush=True)
    return files

def main():
    parser = argparse.ArgumentParser(
        description="Compare files between source and target directories relative to their roots."
    )
    parser.add_argument(
        "source", 
        nargs="?", 
        default=os.environ.get("SOURCE"), 
        help="Source directory (falls back to SOURCE env var)"
    )
    parser.add_argument(
        "target", 
        nargs="?", 
        default=os.environ.get("TARGET"), 
        help="Target directory (falls back to TARGET env var)"
    )
    parser.add_argument(
        "-m", "--matching", 
        action="store_true", 
        help="Output files that exist in both directories instead of target-only files"
    )

    args = parser.parse_args()

    if not args.source or not args.target:
        parser.print_usage(sys.stderr)
        print("Error: Both source and target directories must be specified.", file=sys.stderr)
        sys.exit(1)

    if not os.path.isdir(args.source):
        print(f"Error: Source directory '{args.source}' does not exist.", file=sys.stderr)
        sys.exit(1)
    if not os.path.isdir(args.target):
        print(f"Error: Target directory '{args.target}' does not exist.", file=sys.stderr)
        sys.exit(1)

    source_files = get_relative_files(args.source)
    target_files = get_relative_files(args.target)

    print("Comparing...", file=sys.stderr, flush=True)
    
    if args.matching:
        result = sorted(list(target_files & source_files))
        print(f"Comparison finished. {len(result)} files match in both directories:", file=sys.stderr, flush=True)
    else:
        result = sorted(list(target_files - source_files))
        print(f"Comparison finished. {len(result)} files exist in TARGET but not SOURCE:", file=sys.stderr, flush=True)

    for path in result:
        print(path)

if __name__ == "__main__":
    main()
