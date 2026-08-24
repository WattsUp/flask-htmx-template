"""Model Uniform Resource Identifier encoder/decoder."""

from __future__ import annotations

import random
import secrets

from flask_htmx_template import exceptions as exc

ID_BYTES = 4
ID_BITS = ID_BYTES * 8
URI_BYTES = ID_BYTES * 2  # HEX doubles

TABLE_BITS = 4
TABLE_OFFSET = 32 - TABLE_BITS

MASK_ID = 0xFFFFFFFF >> TABLE_BITS
MASK_TABLE = 0xFFFFFFFF ^ MASK_ID


_ORDER = "big"
_ROUNDS = 3


_cipher: Cipher


class Cipher:
    """Substitution-Permutation network block cipher."""

    def __init__(self, keys: list[int], sbox: list[int], pbox: list[int]) -> None:
        """Create Cipher from keys and boxes.

        Args:
            keys: List of keys
            sbox: Substitution box
            pbox: Permutation box

        """
        self._keys = keys
        self._keys_rev = keys[::-1]

        self._sbox = sbox
        self._sbox_rev = Cipher._reverse_box(sbox)

        self._pbox = pbox
        self._pbox_rev = Cipher._reverse_box(pbox)

    @staticmethod
    def _reverse_box(box: list[int]) -> list[int]:
        """Reverse a box.

        A box maps a location to a new location.
        0 => 1, 1 => 0, 2 => 2 would be the box [1, 0, 2]
        The reversed box is [0, 1, 2]

        Args:
            box: A shuffled range

        Returns:
            The reversed box

        Raises:
            InvalidCipherBoxError: if box is not properly defined

        """
        # Validate box is a box
        n = len(box)
        if min(box) != 0:
            msg = f"Box's minimum should be zero: {box}"
            raise exc.InvalidCipherBoxError(msg)
        if max(box) != (n - 1):
            msg = f"Box's maximum should be n - 1: {box}"
            raise exc.InvalidCipherBoxError(msg)
        if sum(box) != (n * (n - 1) // 2):
            msg = f"Box's sum should be n * (n - 1) / 2: {box}"
            raise exc.InvalidCipherBoxError(msg)
        box_rev = [0] * n
        for i, n in enumerate(box):
            box_rev[n] = i
        return box_rev

    @staticmethod
    def _substitute(n: int, box: list[int]) -> int:
        """Substitute each byte in i with a different on based on box.

        Args:
            n: Input number
            box: Substitution box, shuffled range [0, 255]

        Returns:
            i with each byte shuffled

        """
        out = 0
        for _ in range(ID_BYTES):
            out = (out << 8) | box[n & 0xFF]
            n >>= 8
        return out

    @staticmethod
    def _permutate(n: int, box: list[int]) -> int:
        """Permutate each bit in i to a different location.

        Args:
            n: Input number
            box: Permutation box, shuffed range [0, ID_BITS - 1]

        Returns:
            i with each bit shuffled

        """
        n_bin = format(n, f"0{ID_BITS}b")

        o_bin = [n_bin[p] for p in box]

        return int("".join(o_bin), 2)

    def encode(self, pt: int) -> int:
        """Encode number using a SPN block cipher, reverses _decode.

        Args:
            pt: Plain text number to encode

        Returns:
            Cipher text number

        """
        n = pt
        for i in range(_ROUNDS):
            n ^= self._keys[i]  # XOR with KEYS
            n = self._substitute(n, self._sbox)
            n = self._permutate(n, self._pbox)
        return n ^ self._keys[-1]

    def decode(self, ct: int) -> int:
        """Decode number using a SPN block cipher, reverses _encode.

        Args:
            ct: Cipher text number to decode

        Returns:
            Plain text number

        """
        n = ct
        n ^= self._keys_rev[0]
        for i in range(_ROUNDS):
            n = self._permutate(n, self._pbox_rev)
            n = self._substitute(n, self._sbox_rev)
            n ^= self._keys_rev[i]
        return n

    @staticmethod
    def generate() -> Cipher:
        """Generate a random Cipher.

        Returns:
            Generated Cipher

        """
        keys = [
            int.from_bytes(secrets.token_bytes(ID_BYTES), _ORDER)
            for _ in range(_ROUNDS)
        ]

        sbox = list(range(256))
        random.shuffle(sbox)

        pbox = list(range(ID_BITS))
        random.shuffle(pbox)

        return Cipher(keys, sbox, pbox)

    def to_bytes(self) -> bytes:
        """Convert Cipher to bytes.

        Returns:
            String of bytes containing keys and boxes

        """
        buf = [k.to_bytes(ID_BYTES, _ORDER) for k in self._keys]
        buf.extend((bytes(self._sbox), bytes(self._pbox)))

        return b"".join(buf)

    @staticmethod
    def from_bytes(buf: bytes) -> Cipher:
        """Load Cipher from bytes.

        Args:
            buf: Bytes to load

        Returns:
            Loaded Cipher

        Raises:
            InvalidCipherError: if Cipher fails to load

        """
        n = ID_BYTES * _ROUNDS + 256 + ID_BITS
        if len(buf) != n:
            msg = f"Buf is {len(buf)}B long, expected {n}B"
            raise exc.InvalidCipherError(msg)

        keys: list[int] = []
        for _ in range(_ROUNDS):
            buf_next = buf[:ID_BYTES]
            buf = buf[ID_BYTES:]
            keys.append(int.from_bytes(buf_next, _ORDER))

        sbox = [int(b) for b in buf[:256]]
        pbox = [int(b) for b in buf[256:]]

        return Cipher(keys, sbox, pbox)


def load_cipher(buf: bytes) -> None:
    """Load a Cipher from bytes into _cipher.

    Args:
        buf: Bytes to load

    """
    global _cipher
    _cipher = Cipher.from_bytes(buf)


def id_to_uri(id_: int) -> str:
    """Transform an ID into a URI, reverses uri_to_id.

    Args:
        id_: ID to transform

    Returns:
        URI, hex encoded, 1:1 mapping

    """
    return _cipher.encode(id_).to_bytes(ID_BYTES, _ORDER).hex()


def uri_to_id(uri: str) -> int:
    """Transform a URI into an ID, reverses id_to_uri.

    Args:
        uri: URI to transform

    Returns:
        ID, 1:1 mapping

    Raises:
        InvalidURIError: if uri is not the correct length

    """
    if len(uri) != URI_BYTES:
        msg = f"URI is not {URI_BYTES} bytes long: {uri}"
        raise exc.InvalidURIError(msg)
    try:
        uri_int = int(uri, 16)
    except ValueError as e:
        msg = f"URI is not a hex number: {uri}"
        raise exc.InvalidURIError(msg) from e
    else:
        return _cipher.decode(uri_int)
