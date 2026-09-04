"""Page-number pagination: {count, next, previous, results}, 50 per page, 500 max."""

from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 500
