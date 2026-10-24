import sys

def hesapla(a, op, b):
    a, b = float(a), float(b)
    if op == '+':
        return a + b
    if op == '-':
        return a - b
    if op == '*':
        return a * b
    if op == '/':
        if b == 0:
            raise ZeroDivisionError("Sıfıra bölme yapılamaz")
        return a / b
    raise ValueError(f"Bilinmeyen işlem: {op}")

def main():
    print("Basit Hesap Makinesi")
    print("İşlemler: +, -, *, /")
    while True:
        try:
            satir = input("İşlem (örn: 5 + 3, 'q' için çık): ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if satir.lower() in ('q', 'quit', 'exit'):
            break
        if not satir:
            continue
        parcalar = satir.split()
        if len(parcalar) != 3:
            print("Hatalı format. Örnek: 5 + 3")
            continue
        a, op, b = parcalar
        try:
            sonuc = hesapla(a, op, b)
        except (ValueError, ZeroDivisionError) as e:
            print(f"Hata: {e}")
            continue
        # Tam sayıysa .0 gösterme
        if sonuc == int(sonuc):
            sonuc = int(sonuc)
        print(f"Sonuç: {sonuc}")

if __name__ == '__main__':
    main()