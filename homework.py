import datetime
import logging
import os
import time
from http import HTTPStatus

import requests
import telegram
from dotenv import load_dotenv

import exceptions
import settings


load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

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
        logger.info('Отправлено сообщение.')
    except Exception as err_requests:
        logger.info(f'Не удалось отправить сообщение: {err_requests}')


def get_api_answer(current_timestamp):
    """Делает запрос к единственному эндпоинту API-сервиса.
    В качестве параметра функция получает временную метку.
    Возвращает ответ API, преобразовав из формата JSON к словарю Python.
    """
    timestamp = current_timestamp or int(time.time())
    params = {'from_date': timestamp}  # - 1800 * 24
    try:
        response = requests.get(
            settings.ENDPOINT, headers=HEADERS, params=params
        )
    except Exception as error:
        raise exceptions.CustomAPINotAccessError(
            f'Данные по этому адресу недоступны: {error}'
        )
    try:
        status = response.status_code
    except ValueError:
        raise ValueError('Нет информации о статусе работы.')
    if status != HTTPStatus.OK:
        raise exceptions.CustomStatusError(
            f'Ошибка при запросе к основному API '
            f'{settings.ENDPOINT}: {status}'
        )
    try:
        response = response.json()
    except ValueError as error:
        raise ValueError(f'Данные невозможно преобразовать в JSON: {error}')

    return response


def check_response(response):
    """Проверяет ответ API на корректность.
    Получает ответ API, приведенный к типам данных Python.
    Если ответ API соответствует ожиданиям, то функция должна вернуть:
    список домашних работ по ключу 'homeworks'.
    """
    if not isinstance(response, dict):
        raise TypeError('Данные не являются типом: словарь')
    if 'homeworks' not in response:
        raise KeyError('Ключ homeworks отсутствует.')
    homeworks_list = response['homeworks']

    if not isinstance(homeworks_list, list):
        raise exceptions.CustomNotListError(
            f'Работы хранятся не в виде списка: {homeworks_list}'
        )
    if not homeworks_list:
        raise exceptions.CustomEmptyListError(
            f'Список работ пуст: {response}'
        )

    return homeworks_list


def parse_status(homework):
    """Извлекает из информации о конкретной домашней работе статус этой работы.
    В качестве параметра функция получает только один элемент из списка работ.
    Возвращает строку, с одним из вердиктов словаря HOMEWORK_STATUSES.
    """
    homework_name = homework.get('homework_name')
    if homework_name is None:
        raise KeyError('Ключа homework_name не существует')
    homework_status = homework.get('status')
    if homework_status is None:
        raise KeyError('Ключа homework_status не существует')
    verdict = settings.HOMEWORK_STATUSES.get(homework_status)
    if verdict is None:
        raise KeyError(f'Ключа {homework_status} не существует')

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


def check_message(message, last_message):
    """Сравнивает предыдущий статус работы с вновь полученным.
    Возвращает True если они не равны, чтобы не дублировать сообщения.
    """
    return last_message != message


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


def convert_date(date):
    """Конвертирует строку с датой к timestamp."""
    return datetime.datetime.strptime(
        date, '%Y-%m-%dT%H:%M:%SZ'
    ).timestamp()


def main():
    """Основная логика работы бота: Запрос к API. Проверка ответа.
    Если есть обновления — получить статус работы из обновления.
    И отправить сообщение в Telegram.
    Подождать некоторое время и сделать новый запрос.
    """
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
            date_updated = convert_date(parse_date(homeworks_list[0]))
            if check_message(status, last_message):
                send_message(bot, status)
                last_message = status
            current_timestamp = int(date_updated) or current_timestamp
            time.sleep(settings.RETRY_TIME)

        except Exception as error:
            flag_info = False
            message = f'Сбой в работе программы: {error}'
            if type(error) is exceptions.CustomEmptyListError:
                message = 'На эту дату список работ пуст.'
                flag_info = True
            if check_message(message, last_message):
                send_message(bot, message)
                last_message = message
            logger.error(message) if not flag_info else logger.info(message)
            time.sleep(settings.RETRY_TIME)


if __name__ == '__main__':
    main()
