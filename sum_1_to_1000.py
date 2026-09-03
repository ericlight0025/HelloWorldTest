"""使用 for 迴圈計算 1 到 1000 的總和。"""


def main() -> None:
    """累加 1 到 1000，並輸出結果。"""
    total = 0

    for number in range(1, 1001):
        total += number

    print(total)


if __name__ == "__main__":
    main()
