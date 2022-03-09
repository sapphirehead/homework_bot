import datetime
import logging
import os
import time
from http import HTTPStatus

import requests
import telegram
from dotenv import load_dotenv

import exceptions

load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_TIME = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_STATUSES = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

log_format = ('%(asctime)s - %(name)s - %(levelname)s - %(funcName)s '
              '- %(lineno)d - %(message)s')

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler()
formatter = logging.Formatter(log_format)
handler.setFormatter(formatter)
logger.addHandler(handler)


def send_message(bot, message):
    """Отправляет сообщение в Telegram чат.
    Принимает на вход: экземпляр класса Bot и строку с текстом сообщения.
    """
    try:
        bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=f'Привет, вот статус твоей работы: {message}.'
        )
    except Exception as error:
        logger.info(f'Не удалось отправить сообщение: {error}')


def get_api_answer(current_timestamp):
    """Делает запрос к единственному эндпоинту API-сервиса.
    В качестве параметра функция получает временную метку.
    Возвращает ответ API преобразовав его из формата JSON к типам данных Python.
    """
    timestamp = current_timestamp or int(time.time())
    params = {'from_date': timestamp}  # - 60 * 1800 * 24
    try:
        response = requests.get(ENDPOINT, headers=HEADERS, params=params)
        status = response.status_code
        if status != HTTPStatus.OK:
            raise exceptions.CustomStatusError(
                f'Ошибка при запросе к основному API {ENDPOINT}: {status}'
            )
        response = response.json()
    except Exception as error:
        raise exceptions.CustomAPINotAccessError(
            f'Данные по данному адресу недоступны: {error}'
        )

    return response


def check_response(response):
    """Проверяет ответ API на корректность.
    Получает ответ API, приведенный к типам данных Python.
    Если ответ API соответствует ожиданиям, то функция должна вернуть:
    список домашних работ по ключу 'homeworks'.
    """
    try:
        homeworks_list = response['homeworks']
        if not isinstance(homeworks_list, list):
            raise exceptions.CustomNotListError(
                f'Работы хранятся не в списке: {homeworks_list}'
            )
        if not homeworks_list:
            raise exceptions.CustomEmptyListError(
                f'Список работ пуст: {homeworks_list}'
            )
    except KeyError as error:
        raise KeyError(f'Ключ homeworks отсутствует: {error}')

    return homeworks_list


def parse_status(homework):
    """Извлекает из информации о конкретной домашней работе статус этой работы.
    В качестве параметра функция получает только один элемент из списка работ.
    Возвращает строку, с одним из вердиктов словаря HOMEWORK_STATUSES.
    """
    try:
        homework_name = homework.get('homework_name')
        homework_status = homework.get('status')
        verdict = HOMEWORK_STATUSES.get(homework_status)
        if not all([homework_name, homework_status, verdict]):
            raise KeyError()
    except IndexError as error:
        raise IndexError(f'Нет данных для отображения: {error}')
    except KeyError:
        raise KeyError('Ключа не существует.')
    except ValueError as error:
        raise ValueError(f'Необходимых данных в ответе не содежится: {error}')

    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def parse_date(homework):
    """Извлекает из информации о конкретной домашней работе дату проверки работы.
    В качестве параметра функция получает только один элемент из списка работ.
    Функция возвращает дату чтобы следующая проверка начиналась с неё.
    """
    try:
        homework_date = homework['date_updated']
    except KeyError as error:
        raise KeyError(f'Данных о дате не найдено: {error}')
    except ValueError as error:
        raise ValueError(f'Даты в ответе не содежится: {error}')

    return homework_date


def check_tokens():
    """Проверяет доступность переменных окружения.
    При отсутсвии одной из переменных окружения возвращает False, иначе — True.
    """
    environment_variables = {
        'PRACTICUM_TOKEN': PRACTICUM_TOKEN,
        'TELEGRAM_TOKEN': TELEGRAM_TOKEN,
        'TELEGRAM_CHAT_ID': TELEGRAM_CHAT_ID
    }
    flag = True
    for name, variable in environment_variables.items():
        if not variable:
            logger.critical(f'Не определена переменная окружения {name}.')
            flag = False
            break
    return flag


def main():
    """Основная логика работы бота: Запрос к API. Проверка ответа.
    Если есть обновления — получить статус работы из обновления.
    И отправить сообщение в Telegram.
    Подождать некоторое время и сделать новый запрос.
    """
    err_count = 0
    last_message = ''
    if check_tokens():
        bot = telegram.Bot(token=TELEGRAM_TOKEN)
        current_timestamp = int(time.time())
    else:
        raise exceptions.CustomTokenError(
            'Не определена переменная окружения.'
        )

    while True:
        try:
            response = get_api_answer(current_timestamp)
            homeworks_list = check_response(response)
            status = parse_status(homeworks_list[0])
            date_updated = parse_date(homeworks_list[0])
            date_updated = datetime.datetime.strptime(
                date_updated, '%Y-%m-%dT%H:%M:%SZ'
            ).timestamp()
            send_message(bot, status)
            logger.info('Сообщение удачно отправлено.')
            current_timestamp = int(date_updated) or current_timestamp
            time.sleep(RETRY_TIME)

        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            if err_count < 1 and last_message != message:
                send_message(bot, message)
                last_message = message
                err_count = 0
            logger.error(message)
            err_count += 1
            time.sleep(RETRY_TIME)


if __name__ == '__main__':
    main()
