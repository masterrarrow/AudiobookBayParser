from bs4 import BeautifulSoup
from requests import get
from multiprocessing import Pool, freeze_support
from datetime import datetime, timedelta
from functools import partial
from docxtpl import DocxTemplate, InlineImage
from docx.shared import Mm
from shutil import copyfileobj
from decouple import config
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from django.template import Template, Context
from django.template.engine import Engine
from django.conf import settings
from re import split, search
from os import makedirs, path
from book import Book
import logging


def get_page(period: datetime.date, url: str):
    """
        Get book page url for book post and pass it to the process_book_page() function

        :param period: Period of days for which to show data (current date - days)
        :param url: Category page url
        :return: Pages urls
    """
    page_data = get(url).text
    soup = BeautifulSoup(page_data, 'lxml')
    posts = soup.findAll('div', {'class': 'post'})

    page_url = []

    # For all posts
    for post in posts:
        # Get new books only for the certain period of time
        audio_data = post.find('p', {'style': 'text-align:center;'}).text
        # Get book post publication date
        date_time_str, _ = audio_data.split('Format:')
        date_time_str = date_time_str[8:]
        post_data = datetime.strptime(date_time_str, '%d %b %Y')
        post_data = post_data.date()

        if post_data >= period:
            page_url.append(post.findAll('p', {'class': 'center'})[1].find('a').get('href'))

    return page_url


def process_book_page(save_to_word: bool, page_url: str):
    """
        Get book information

        :param save_to_word: Save data tpo Ms Word
        :param page_url: Book page url
        :return: {'book': Book, 'saved': True/False if save_to_word is True else None}
    """
    book_page = get(page_url).text
    soup = BeautifulSoup(book_page, 'lxml')
    post = soup.find('div', {'class': 'post'})

    # Get book information
    title = post.find('div', {'class': 'postTitle'}).text.strip()
    book_info, _ = post.find('div', {'class': 'postInfo'}).text.strip().split('Keywords:')

    # Book categories and language
    _, book_categories = split('[C].*:', book_info)
    book_categories, book_language = split('\n[L].*:', book_categories)

    content = post.find('div', {'class': 'postContent'})
    link = content.findAll('p', {'class': 'center'})[1]

    # Book image and page link
    book_link = link.find('a').get('href')
    book_image = link.find('img').get('src')

    description = content.find('div', {'class': 'desc'})
    audio_data = description.find('p', {'style': 'left;'}).text

    # Book details
    author, audio_data = audio_data.split(' Read by ')
    author = author.replace('Written by ', '')
    read, audio_data = split(' [F].*t: ', audio_data)

    if search(r' [U]', audio_data):
        bitrate, _ = split(' [U]', audio_data)
        unabridged = True
    else:
        bitrate = audio_data.strip()
        unabridged = False

    if search(r' [B].*: ', audio_data):
        audio_format, audio_data = split(' [B].*: ', audio_data)
    else:
        audio_format = None

    book = Book(title, book_categories, book_language, book_link, book_image,
                author, read, audio_format, bitrate, unabridged)

    if save_to_word:
        return {'book': book, 'saved': save_doc(book)}
    else:
        return {'book': book, 'saved': None}


def save_doc(book: Book):
    """
        Save book information into MS Word

        :param book: Book information
        :return: True/False
    """
    try:
        doc = DocxTemplate('Template.docx')
        # Save image
        response = get(book.cover, stream=True)
        *_, image_path = book.cover.split('/')
        directory = 'docs/pict/'
        image_path = directory + image_path

        # Make dirs for files
        if not path.exists(directory):
            makedirs(directory)

        with open(image_path, 'wb') as f:
            copyfileobj(response.raw, f)
        del response

        # Write data to MS Word
        image = InlineImage(doc, image_path, width=Mm(120))

        context = {'Title': book.title,
                   'Categories': book.categories,
                   'Language': book.language,
                   'Cover': image,
                   'Link': book.link,
                   'Author': book.author,
                   'Read': book.read,
                   'Format': book.audio_format,
                   'Bitrate': book.bitrate,
                   'Unabridged': 'Unabridged' if book.unabridged else ''}
        doc.render(context)
        doc.save(f"docs/{book.title}.docx")
    except:
        return False

    return True


def send_notification(books: list):
    """
        Send email via SendGrid

        :param books: book list
        :return: True/False
    """
    # Read template file
    with open('Template.html', 'r') as file:
        data = file.read()

    # Using Django template create email content
    settings.configure(DEBUG=False)
    template = Template(data, engine=Engine())
    context = Context({'books': books})
    output = template.render(context)

    message = Mail(
        from_email=config('FROM_EMAIL'),
        to_emails=config('TO_EMAIL'),
        subject='Audiobooks Newsletter (AudiobookBay)',
        html_content=output)
    try:
        sg = SendGridAPIClient(config('SENDGRID_API_KEY'))
        response = sg.send(message)
        if response.status_code != 202:
            # Cannot send email
            return False
    except:
        return False

    return True


def main(books_category: str, pages_count: int, period: datetime.date, save_to_word: bool = True):
    """
        Find books for some period of time in some category

        :param books_category: Books category (action, adventure ...)
        :param pages_count: Number of first pages on which to search
        :param period: Post data from which to select books
        :param save_to_word: True - save retrieved information to MS Word, False - send it via email
        :return: None
    """
    # Url for books category page
    base_url = f'http://audiobookbay.nl/audio-books/type/{books_category}/'

    # Log file
    logging.basicConfig(filename="parser.log", level=logging.INFO)

    # Pages urls (page 0 = page 1)
    urls = [base_url + f'page/{page}/' for page in range(pages_count) if page != 1]

    # Get new books for the certain period of time
    params = partial(get_page, period)
    p = Pool(processes=10)
    books_urls = p.map(params, urls)
    p.close()
    p.join()

    # Flatten a list of lists, exclude empty lists
    books_urls = [item for sublist in books_urls if len(sublist) != 0 for item in sublist]

    if len(books_urls) == 0:
        logging.log(logging.INFO, 'New books has not been found!')
        exit(0)

    logging.log(logging.INFO, 'New books has been found!')

    # Get books information
    param = partial(process_book_page, save_to_word)
    pool = Pool(processes=10)
    results = pool.map(param, books_urls)
    pool.close()
    pool.join()

    # Save retrieved information to MS Word
    if save_to_word:
        for result in results:
            if not result['saved']:
                data = result['book']
                logging.log(logging.ERROR, 'Saving book ', data.title, ' has been failed!')
                exit(0)
        logging.log(logging.INFO, 'All new books has been successfully saved!')
    else:
        # Send email with retrieved information
        books = [result['book'] for result in results]

        if not send_notification(books):
            logging.log(logging.ERROR, 'Sending newsletter has been failed')
            exit(0)

        logging.log(logging.INFO, 'Newsletter has been send!')


if __name__ == '__main__':
    # Books category
    category = config('CATEGORY')

    # Number of first pages on which to search (pages - 1)
    pages = 4

    # Period for which to show data (in days -> current date - days)
    days = 3
    period_days = datetime.today().date() - timedelta(days=days)
    # endregion Initial data

    freeze_support()
    # books_category, pages_count, period, save_to_word
    main(category, pages, period_days, False)
