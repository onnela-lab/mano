import logging
import sys
from copy import deepcopy
from os import name
from os.path import abspath
from sys import argv as command_line_args

from mano.constants import VALID_EXTENSIONS_ANDED, logger as log
from mano.file_management import compress_zstd_files, decompress_zstd_files


log.setLevel(logging.DEBUG)


def main():
    
    log.warning(f"mano received the following cli args: {sys.argv}")
    if len(sys.argv) < 2:
        log.info("\n")
        log.info("mano currently supports 2 commands: decompress and compress")
        log.info("\n")
        log.info("decompress <directory_path> [--delete-zst] [--overwrite]")
        log.info("\tThis command will decompress all .zst files in the specified directory.")
        log.info("\t(You can specify the current directory with a single dot: `.`)")
        log.info("\n")
        log.info("compress <directory_path> [--delete-original] [--overwrite]")
        log.info("\tThis command will compress all .zst files in the specified directory.")
        log.info("\t(You can specify the current directory with a single dot: `.`)")
        log.info("\n")
        return
    
    args = deepcopy(command_line_args[1:])
    
    if "decompress" == args[0]:
        decompress(args)
        exit()
    elif "compress" == args[0]:
        compress(args)
        exit()
    else:
        log.error(f"unknown command: `{args}`")
        exit(1)


#
## "User Interface" helpers"
#


def confirm(*args: str):
    
    log.info("\nPlease confirm you want to:")
    describe_actions(args)
    response = input("(y/n): ").strip().lower()
    
    if response == "y" or response == "yes":
        log.info("proceeding...")
        return
    
    log.error("exiting, doing nothing.")
    exit(0)


def describe_actions(actions: tuple[str, ...]):
    for action in actions:
        log.info(f"\t- {action}")


#
## Commands
#


def decompress(args: list[str]):
    ensure_minimum_number_of_args("decompress", args, 2)
    
    directory_path = args[1]
    delete_zst = "--delete-zst" in args
    overwrite = "--overwrite" in args
    
    decompress_summary = {
        "delete_zst": {
            True: "DELETE the .zst files after decompressing them",
            False: "RETAIN any .zst files after decompressing them"
        },
        "overwrite": {
            True: "OVERWRITE any existing files",
            False: "SKIP any files that already exist"
        },
    }
    confirm(
        f"Decompress all .zst files in the directory `{abspath(directory_path)}` and it's subdirectories.",
        decompress_summary["delete_zst"][delete_zst],
        decompress_summary["overwrite"][overwrite],
    )
    decompress_zstd_files(directory_path, delete_zsts=delete_zst, overwrite=overwrite)


def compress(args: list[str]):
    ensure_minimum_number_of_args("compress", args, 2)
    
    # todo: make this look like the above decompress function style
    
    directory_path = args[1]
    delete_original = "--delete-original" in args
    overwrite = "--overwrite" in args
    
    description = [
        f"Compress all {VALID_EXTENSIONS_ANDED} files in the directory `{abspath(directory_path)}` "
        "and it's subdirectories."
    ]
    if delete_original:
        description.append("DELETE the original files after compressing them")
    else:
        description.append("RETAIN the original files after compressing them")
    if overwrite:
        description.append("OVERWRITE any existing .zst files")
    else:
        description.append("SKIP any .zst files that already exist")
    
    confirm(*description)
    compress_zstd_files(directory_path, delete_original=delete_original, overwrite=overwrite)


#
# Validation
#


def ensure_minimum_number_of_args(
    command_name: str, args: list[str], minimum_including_command_itself: int
):
    if len(args) < minimum_including_command_itself:
        
        log.error(
            "\n"
            f"insufficient arguments, `{command_name}` expected at least "
            f"{minimum_including_command_itself}, but got {len(args)}."
        )
        log.error(f"\targs: {args}\n")
        exit(1)




if name == "__main__":
    raise NotImplementedError(
        "This file is not meant to be run directly. Please run 'mano' from the command line."
    )
