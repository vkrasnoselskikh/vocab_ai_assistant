from vocab_llm_bot.app import UserDialogCtx
from vocab_llm_bot.dict_file import DictFile
from colorama import Fore, Style


def main():
    try:
        diag_ctx = UserDialogCtx(dict_file=DictFile())

        while True:
            message = diag_ctx.next_word()

            print(Fore.LIGHTCYAN_EX + Style.BRIGHT + message + Fore.GREEN)
            user_input = input()
            resp = diag_ctx.analyze_user_input(user_input)
            print(Fore.LIGHTMAGENTA_EX + resp )

    finally:
        print(Style.RESET_ALL)


if __name__ == '__main__':
    main()
