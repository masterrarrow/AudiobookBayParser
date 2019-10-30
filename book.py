class Book:
    """
        Class for storing information about book
    """
    def __init__(self, title: str, categories: str, language: str, link: str, cover: str,
                 author: str, read: str, audio_format: str, bitrate: str, unabridged: bool):
        self.title = title
        self.categories = categories
        self.link = link
        self.language = language
        self.cover = cover
        self.author = author
        self.read = read
        self.audio_format = audio_format
        self.bitrate = bitrate
        self.unabridged = unabridged

    def __str__(self):
        return f'{self.title} - {self.author}'

    def __repr__(self):
        class_name = type(self).__name__
        return f'{class_name}({self.title!r}, {self.author!r})'

    @property
    def title(self):
        return self.__title

    @title.setter
    def title(self, title):
        if title:
            self.__title = title
        else:
            raise Exception('The book should have a title!')

    @property
    def author(self):
        return self.__author

    @author.setter
    def author(self, author):
        if author:
            self.__author = author
        else:
            raise Exception('The book must have an author!')
