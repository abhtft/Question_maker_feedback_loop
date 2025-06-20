import os
import logging
from datetime import datetime

def setup_logging():
    # Ensure 'logging' directory exists
    log_dir = "logging"
    os.makedirs(log_dir, exist_ok=True)

    # Create log filename with timestamp
    log_filename = f"{log_dir}/app_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    # Correct logging configuration
    logging.basicConfig(
        filename=log_filename,
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Create a logger
    logger = logging.getLogger()
    
    # Optional: Add console output as well
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    return logger

# Example usage
def main():
    logger = setup_logging()
    
    try:
        # Your application logic here
        logger.info("Application started")
        logger.warning("This is a warning message")
        logger.error("This is an error message")
        
        # Simulating some operation
        result = 10 / 2
        logger.info(f"Calculation result: {result}")
    
    except Exception as e:
        logger.exception("An error occurred")

if __name__ == "__main__":
    main()