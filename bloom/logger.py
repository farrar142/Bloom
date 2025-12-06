import logging
import sys


logger = logging.getLogger(__name__)


def get_logger() -> logging.Logger:
    """bloom용 로거를 반환합니다.

    uvicorn 실행 시 uvicorn의 로그 설정을 따르도록 합니다.
    """
    # uvicorn이 실행 중인지 확인 (uvicorn은 루트 로거에 핸들러를 추가함)
    root_logger = logging.getLogger()
    if root_logger.handlers:
        # uvicorn이 설정한 핸들러가 있으면 그대로 사용
        if not logger.handlers:
            logger.setLevel(root_logger.level)
            logger.addHandler(root_logger.handlers[0])
    else:
        # uvicorn이 없으면 기본 설정
        if not logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)

    return logger
