class InvalidTipoEventoError(ValueError):
    """Raised when a procEventoNFe has an unrecognised tpEvento."""

    def __init__(self, tp_evento):
        self.tp_evento = tp_evento
        super().__init__(f"Tipo de evento inválido: {tp_evento}")
