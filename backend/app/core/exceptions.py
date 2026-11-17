class CricketCanvasError(Exception):
    status_code = 500


class NotFoundError(CricketCanvasError):
    status_code = 404


class ValidationFailure(CricketCanvasError):
    status_code = 422
