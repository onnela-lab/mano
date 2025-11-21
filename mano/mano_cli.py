import logging
import sys
from copy import deepcopy
from os import name
from os.path import abspath
from pprint import pprint
from sys import argv as command_line_args

from mano.constants import InternalError, logger as log, VALID_EXTENSIONS_ANDED
from mano.file_management import compress_zstd_files, decompress_zstd_files


log.setLevel(logging.DEBUG)

# list all double-dashed parameters here
DELETE_ZST = "--delete-zst"
OVERWRITE = "--overwrite"
DELETE_ORIGINAL = "--delete-original"



def main():
    log.debug(f"mano received the following cli args: {sys.argv}")
    
    # (when main is called sys.argv[0] should always be the script's name.)
    # Display help on no args, -h, --help
    if len(sys.argv) < 2 or "-h" in sys.argv or "--help" in sys.argv:
        log.info("\n")
        log.info("mano currently supports 2 commands: decompress and compress")
        log.info("\n")
        log.info(f"decompress <directory_path> [{DELETE_ZST}] [{OVERWRITE}]")
        log.info("\tThis command will decompress all .zst files in the specified directory.")
        log.info("\t(You can specify the current directory with a single dot: `.`)")
        log.info("\n")
        log.info(f"compress <directory_path> [{DELETE_ORIGINAL}] [{OVERWRITE}]")
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


def confirm_command(*args: str):
    """
    Provide any number of strings describing exactly what is about to happen.
    The first parameter should be a general description, subsequent parameters
    should describe the state of every option/flag whether it was provided or not.
    """
    
    for arg in args:
        if not isinstance(arg, str):  # type: ignore
            raise InternalError("confirm() only accepts string arguments")
    
    # display, confirm, exit or proceed.
    log.info("\nPlease confirm you want to:")
    for arg in args:
        log.info(f"\t- {arg}")
    
    response = input("(y/n): ").strip().lower()
    if response == "y" or response == "yes":  # don't get fancy, just y and yes
        log.info("proceeding...")
        return
    
    log.error("")  # blank line for readability
    log.error("Exiting mano, no actions were taken.")
    exit(0)


#
## Commands
#


def decompress(args: list[str]):
    ensure_minimum_number_of_args("decompress", args, 2)
    ensure_only_allowed_parameters("decompress", args, [DELETE_ZST, OVERWRITE])
    
    # file path must come before delete_zst and overwrite (index 1)
    directory_path = args[1]
    delete_zst = DELETE_ZST in args
    overwrite = OVERWRITE in args
    
    class info:
        describe = \
            f"Decompress all .zst files in the directory `{abspath(directory_path)}` and it's subdirectories."
        delete_zst = {
            True: "DELETE the .zst files after decompressing them",
            False: "RETAIN any .zst files after decompressing them"
        }
        overwrite = {
            True: "OVERWRITE any existing files",
            False: "SKIP any files that already exist"
        }
    
    confirm_command(
        info.describe,
        info.delete_zst[delete_zst],
        info.overwrite[overwrite],
    )
    try:
        decompress_zstd_files(directory_path, delete_zsts=delete_zst, overwrite=overwrite)
    except Exception:
        exit(2)


def compress(args: list[str]):
    ensure_minimum_number_of_args("compress", args, 2)
    ensure_only_allowed_parameters("compress", args, [DELETE_ORIGINAL, OVERWRITE])
    
    # file path must come before delete_original and overwrite (index 1)
    directory_path = args[1]
    delete_original = DELETE_ORIGINAL in args
    overwrite = OVERWRITE in args
    
    class command_info:
        describe = \
            f"Compress all {VALID_EXTENSIONS_ANDED} files in the directory " \
                f"`{abspath(directory_path)}` and it's subdirectories."
        delete_original = {
            True: "DELETE the original files after compressing them",
            False: "RETAIN the original files after compressing them"
        }
        overwrite = {
            True: "OVERWRITE any existing .zst files",
            False: "SKIP any .zst files that already exist"
        }
    
    confirm_command(
        command_info.describe,
        command_info.delete_original[delete_original],
        command_info.overwrite[overwrite],
    )
    
    try:
        compress_zstd_files(directory_path, delete_original=delete_original, overwrite=overwrite)
    except Exception:
        exit(2)


#
# Validation
#


def ensure_minimum_number_of_args(
    command_name: str,
    args: list[str],
    minimum_required_argument_count_including_the_command_itself: int,
):
    _confirm_arg_matches_name(command_name, args)
    
    # Display a useful error about missing arguments, then exit with a non-zero status.
    if len(args) < minimum_required_argument_count_including_the_command_itself:
        log.error(
            "\n"
            f"insufficient arguments, `{command_name}` expected at least "
            f"{minimum_required_argument_count_including_the_command_itself}, but got {len(args)}."
        )
        # log.error(f"\targs: {args}\n")
        exit(1)


def ensure_only_allowed_parameters(command_name: str, args: list[str], allowed_parameters: list[str]):
    """
    Currently a check for exact match of allowed parameters only.
    """
    _confirm_arg_matches_name(command_name, args)
    
    
    # Display a useful error about _all_ unrecognized parameters, then exit with a non-zero status.
    any_bad_params = False
    for arg in args[1:]:
        if arg not in allowed_parameters:
            log.error(f"\nUnknown parameter '{arg}' provided to command '{args[0]}'.\n")
            any_bad_params = True
    
    if any_bad_params:
        exit(1)


def _confirm_arg_matches_name(command_name: str, args: list[str]):
    """ Ensure the first argument matches the command name. """
    if command_name != args[0]:
        raise InternalError(
            f"'{command_name}' does not match first arg '{args[0]}' passed to argument validation"
        )


if name == "__main__":
    raise NotImplementedError(
        "This file is not meant to be run directly. Please run 'mano' from the command line."
    )
