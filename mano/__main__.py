# just run the mano cli main function
from mano.constants import logger as log
if __name__ == "__main__":
    from mano.mano_cli import main
    log.debug("running main from __main__")
    main()
