import logging
import sys
from copy import deepcopy
from os import name
from os.path import abspath
from sys import argv as command_line_args

from mano.constants import BEIWE_EXTENSIONS_ANDED, GlobalSettings, InternalError, logger as log
from mano.file_management import (check_is_valid_beiwe_data_file, compress_to_zst_files,
    decompress_zst_files, validate_is_a_folder_or_valid_beiwe_data_file,
    validate_is_a_folder_or_zst_file)
from mano.messages import BAD_MULTITHREADING_ERROR, TOO_MANY_MULTITHREAD_ARGS


log.setLevel(logging.DEBUG)

# list of all commands
COMPRESS = "compress"
DECOMPRESS = "decompress"

# list all double-dashed parameters here
DELETE_ZST = "--delete-zst"
OVERWRITE = "--overwrite"
DELETE_ORIGINAL = "--delete-original"
MULTITHREAD_PREFIX = "--mt"


PARAMETERS_BY_COMMAND = {
    DECOMPRESS: [DELETE_ZST, OVERWRITE],
    COMPRESS: [DELETE_ORIGINAL, OVERWRITE],
}

CLI_HELP_MESSAGE = f"""
mano currently supports 2 commands: decompress and compress.
  Parameters inside [brackets] are optional.
  <Parameters in angle brackets> are required.
  `text inside backticks are examples`

~File Management~


"mano decompress <folder or file path> [{DELETE_ZST}] [{OVERWRITE}]" 
  This command will decompress all compressed Beiwe data files ending in .zst to the specified folder
  (Specify the current folder with a single dot: `.` or `./`)


"mano compress <folder or file path> [-#] [{DELETE_ORIGINAL}] [{OVERWRITE}]"
  This command will compress all Beiwe data files in the specified folder.

  You can optionally provide a `-#` (like `-8`) to set a specific compression level.
    (The default of 2 matches downloaded data, the maximum is 22, the maximum gains from
    a higher value can be up to about 30% smaller. High values get _very_ slow.)


Global Options - you can always provide these with any command:

  Add  `-y`  or  `--yes`  to skip all user interaction prompts.

  Add  `--mt#`  (where # is a number) to set the number of threads Mano will use.
    For example  `--mt1`  and  `--mt10`  will set Mano to use 1 or 10 threads.
    `--mt0`  will use all CPU threads available, and is the default behavior.
    (Mano is usually limited by storage device speed, except when compressing at a high
    compression level.)
    Multithreading does not apply to data download operations.

  Examples:

    [Decompress]
        `mano decompress ./abcde12345/ --delete-zst --overwrite` -y
    This will skip confirmation and immediately decompress all .zst files in the `abcde12345/` 
    folder and subfolders, deleting the .zst files, and overwriting any uncompressed files
    that already exist and share that name.

    [Compress]
        `mano compress ./12345abcde/ -10 --delete-original` --mt4
    This will prompt you to continue, then use 4 threads to compress all Beiwe data files in
    the `./12345abcde/` folder and subfolders using compression level 10, and delete the
    original uncompressed files.  If it encounters a file that when compressed would overwrite
    an existing .zst file, Mano will raise an Error and stop execution.

"""  # retain final new line.


def main():
    # reset global settings to default CLI values
    GlobalSettings.skip_user_interaction = False
    log.debug(f"mano received the following cli args: {sys.argv}")
    
    # Display help on no args, -h, --help
    # (when main is called sys.argv[0] should always be the script's name.)
    if len(sys.argv) < 2 or "-h" in sys.argv or "--help" in sys.argv:
        for line in CLI_HELP_MESSAGE.split("\n"):  # do not change to splitlines
            log.info(line)                         # we want blank lines retained
        return
    
    args = deepcopy(command_line_args[1:])  # drop the program name from args
    
    # handle global parameters first, remove from args
    if "-y" in args or "--yes" in args:
        GlobalSettings.skip_user_interaction = True
        args.remove("-y") if "-y" in args else args.remove("--yes")
    
    extract_multithread_args(args)  # removes all --mt# args from args
    the_command = args.pop(0)
    
    # dispatch to the appropriate command
    if the_command == DECOMPRESS:
        decompress(args)
    elif the_command == COMPRESS:
        compress(args)
    else:
        log.error(f"unknown command: `{args}`")
        exit(1)
    
    exit(0)


# todo - some message indicating the number of threads being used
# todo: build tests
def extract_multithread_args(args: list[str]):
    indices = [i for i, arg in enumerate(args) if arg.startswith(MULTITHREAD_PREFIX)]
    indices.sort(reverse=True)  # reverse so we can remove items safely
    mt_args = [args.pop(i) for i in indices]  # removes all the --mt args
    
    # return early if there were none, error out if there are multiple
    if len(mt_args) == 0:
        
        return
    if len(mt_args) > 1:
        log.error(TOO_MANY_MULTITHREAD_ARGS)
        exit(1)
    
    arg = mt_args[0]  # len is 1, string starting with "--mt"
    try:
        thread_count = int(arg[4:])
    except ValueError:
        log.error(BAD_MULTITHREADING_ERROR(arg))
        exit(1)
    
    GlobalSettings.multithreading_count = thread_count


#
## "User Interface" helpers"
#


def confirm_command(*args: str):
    """
    Provide any number of strings describing exactly what is about to happen.
    The first parameter should be a general description, subsequent parameters
    should describe the state of every option/flag whether it was provided or not.
    """
    if GlobalSettings.skip_user_interaction:
        return
    
    for arg in args:
        if not isinstance(arg, str):  # type: ignore
            raise InternalError("confirm_command() only accepts string arguments")
    
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
    ensure_minimum_number_of_args(DECOMPRESS, args, 1)
    ensure_only_allowed_parameters(DECOMPRESS, args, [DELETE_ZST, OVERWRITE], args[0])
    
    # file path must come before delete_zst and overwrite (index 0)
    target_path = args[0]
    delete_zst = DELETE_ZST in args
    overwrite = OVERWRITE in args
    
    validate_is_a_folder_or_zst_file(target_path)
    
    class info:
        describe = \
            f"Decompress all .zst files in the folder `{abspath(target_path)}` and its subfolders."
        delete_zst = {
            True: "DELETE the .zst files after decompressing them",
            False: "RETAIN any .zst files after decompressing them"
        }
        overwrite = {
            True: "OVERWRITE any existing files",
            False: "SKIP any files that already exist"
        }
    if target_path.endswith('.zst'):
        info.describe = f"Decompress the .zst file `{abspath(target_path)}`"
        info.delete_zst = {
            True: "DELETE the .zst file when finished",
            False: "RETAIN the .zst file when finished"
        }
        info.overwrite = {
            True: "OVERWRITE the existing file",
            False: "SKIP it if a file already exists"
        }
    
    confirm_command(
        info.describe,
        info.delete_zst[delete_zst],
        info.overwrite[overwrite],
    )
    try:
        decompress_zst_files(target_path, delete_zsts=delete_zst, overwrite=overwrite)
    except Exception:
        # simple statement of what failed, details should be printed in the called functions.
        # TODO: improve logging of exceptions
        log.error("An error occurred while decompressing .zst files.")
        exit(2)


def compress(args: list[str]):
    ensure_minimum_number_of_args(COMPRESS, args, 1)
    compression_level = extract_compression_level(args)  # removes -# from args if present
    ensure_only_allowed_parameters(COMPRESS, args, [DELETE_ORIGINAL, OVERWRITE], args[0])
    
    # file path must come before delete_original and overwrite (index 0)
    target_path = args[0]
    delete_original = DELETE_ORIGINAL in args
    overwrite = OVERWRITE in args
    
    validate_is_a_folder_or_valid_beiwe_data_file(target_path)
    
    class info:
        compression_level: str  # (type annotation for attribute, checker complains without this line)
        describe = \
            f"Compress all {BEIWE_EXTENSIONS_ANDED} files in the folder " \
                f"`{abspath(target_path)}` and its subfolders."
        delete_original = {
            True: "DELETE the original files after compressing them",
            False: "RETAIN the original files after compressing them"
        }
        overwrite = {
            True: "OVERWRITE any existing .zst files",
            False: "SKIP any .zst files that already exist"
        }
    if check_is_valid_beiwe_data_file(target_path):
        info.describe = f"Compress the file `{abspath(target_path)}`"
        info.delete_original = {
                True: "DELETE the original file after compressing it",
                False: "RETAIN the original file after compressing it"
            }
        info.overwrite = {
                True: "OVERWRITE any existing .zst file",
                False: "SKIP if a .zst file already exists"
            }
    
    info.compression_level = f"using compression level {compression_level}"
    if compression_level == 2:  # default
        info.compression_level += " (the default)"
    
    confirm_command(
        info.describe,
        info.delete_original[delete_original],
        info.overwrite[overwrite],
        info.compression_level,
    )
    
    try:
        compress_to_zst_files(
            target_path,
            delete_original=delete_original,
            overwrite=overwrite,
            compression_level=compression_level,
        )
    except Exception:
        # simple statement of what failed, details should be printed in the called functions.
        # TODO: improve logging of exceptions
        log.error("An error occurred while compressing zstd files.")
        exit(2)


def extract_compression_level(args: list[str]) -> int:
    """ look for a -# parameter in args, where # is an integer from 0 to 22. """
    level_str = "-2"  # default compression level
    for arg in args:
        # only digits after a single dash
        if arg.startswith('-') and len(arg) >= 2 and arg[1:].isdigit():
            level_str = arg
            args.remove(arg)  # remove from args only if found
            break
    
    # validate level between 0 and 22
    level = int(level_str[1:])
    if not (0 <= level <= 22):
        log.error(f"Invalid compression level `{level}` provided. Must be between 0 and 22.")
        exit(1)
    
    return level


#
# Validation
#


def ensure_minimum_number_of_args(
    command_name: str,
    args: list[str],
    minimum_required_argument_count_including_the_command_itself: int,
):
    # Display a useful error about missing arguments, then exit with a non-zero status.
    if len(args) < minimum_required_argument_count_including_the_command_itself:
        log.error(
            "\n"
            f"insufficient arguments, `{command_name}` expected at least "
            f"{minimum_required_argument_count_including_the_command_itself}, but got {len(args)}."
        )
        # log.error(f"\targs: {args}\n")
        exit(1)


def ensure_only_allowed_parameters(
    command_name: str, args: list[str], allowed_parameters: list[str], file_path_parameter: str|None = None
):
    """
    Currently a check for exact match of allowed parameters only.
    """
    # Display a useful error about _all_ unrecognized parameters, then exit with a non-zero status.
    any_bad_params = False
    for arg in args:
        if arg is file_path_parameter:
            continue
        if arg not in allowed_parameters:
            log.error(f"\nUnknown parameter `{arg}` provided to command `{command_name}`.\n")
            any_bad_params = True
            log.info("Allowed parameters are:")
            for param in sorted(PARAMETERS_BY_COMMAND[command_name]):
                log.info(f"\t{param}")
    
    if any_bad_params:
        exit(1)


if name == "__main__":
    raise NotImplementedError(
        "This file is not meant to be run directly. Please run 'mano' from the command line."
    )
