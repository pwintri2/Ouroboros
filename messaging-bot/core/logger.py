import logging

class BotLogger:
    def __init__(self, log_file="bot.log"):
        logging.basicConfig(
            filename=log_file,
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s"
        )
        self.logger = logging.getLogger("BotLogger")

    def log(self, message):
        self.logger.info(message)

    def error(self, message):
        self.logger.error(message)
