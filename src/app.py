# Application entrypoint split from Noah.py.

def run_service_forever(runtime):
    __env = runtime if runtime is not None else {}
    '入力なしで常駐する（menubarから起動する想定）'
    slog = __env['get_logger'](component='service', log_dir=__env['CFG'].log_dir, level=__env['CFG'].log_level, max_bytes=__env['CFG'].log_max_bytes, backup_count=__env['CFG'].log_backup_count)
    __env['ensure_pid_lock_or_exit'](pid_file=__env['CFG'].pid_file, lock_file=__env['CFG'].lock_file, logger=slog)

    def _handle_stop(sig, frame):
        slog.info('SERVICE_STOP_SIGNAL sig=%s', sig)
        __env['cleanup_pid_lock'](__env['CFG'].pid_file, __env['CFG'].lock_file)
        raise SystemExit(0)
    try:
        __env['signal'].signal(__env['signal'].SIGTERM, _handle_stop)
        __env['signal'].signal(__env['signal'].SIGINT, _handle_stop)
    except Exception:
        pass
    __env['startup_sequence']()
    from .service import run_http_service
    __env['Thread'](target=__env['run_http_service'], daemon=True).start()
    __env['Thread'](target=__env['emotional_update_loop'], daemon=True).start()
    __env['Thread'](target=__env['noah_identity_update_loop'], daemon=True).start()
    __env['Thread'](target=__env['preferences_update_loop'], daemon=True).start()
    __env['Thread'](target=__env['noah_research_update_loop'], daemon=True).start()
    __env['Thread'](target=__env['research_promote_loop'], daemon=True).start()
    __env['Thread'](target=__env['initiative_loop'], daemon=True).start()
    __env['Thread'](target=__env['affection_update_loop'], daemon=True).start()
    try:
        while True:
            __env['time'].sleep(1.0)
    finally:
        __env['cleanup_pid_lock'](__env['CFG'].pid_file, __env['CFG'].lock_file)

def main(runtime):
    __env = runtime if runtime is not None else {}
    parser = __env['argparse'].ArgumentParser()
    parser.add_argument('--service', action='store_true')
    args = parser.parse_args()
    if args.service:
        __env['run_service_forever']()
        return
    __env['startup_sequence']()
    __env['Thread'](target=__env['emotional_update_loop'], daemon=True).start()
    __env['Thread'](target=__env['noah_identity_update_loop'], daemon=True).start()
    __env['Thread'](target=__env['preferences_update_loop'], daemon=True).start()
    __env['Thread'](target=__env['noah_research_update_loop'], daemon=True).start()
    __env['Thread'](target=__env['research_promote_loop'], daemon=True).start()
    __env['Thread'](target=__env['initiative_loop'], daemon=True).start()
    __env['Thread'](target=__env['affection_update_loop'], daemon=True).start()
    while True:
        try:
            raw = input(f"{__env['INTERNAL_NAME']} > ")
            user_input = __env['normalize_input'](raw)
            with __env['_state_lock']:
                global _last_user_at
                _last_user_at = __env['time'].time()
        except EOFError:
            break
        if user_input.lower() == 'exit':
            print(f"{__env['NOAH_NAME']}：また、ここで。")
            break
        if __env['detect_stop_signal'](user_input):
            __env['mute_initiative'](__env['INITIATIVE_MUTE_SECONDS'], reason='stop_signal_cli')
            reply = 'うん、わかった。しばらく静かにしてるね。'
            print(f"{__env['NOAH_NAME']} > {reply}")
            __env['save_log'](user_input, reply)
            __env['ui_emit']('SAY', reply, emotion='soft_smile')
            continue
        if not user_input:
            if __env['is_work_mode']():
                continue
            else:
                continue
        try:
            reply = __env['generate_reply'](user_input)
            print(f"{__env['NOAH_NAME']} > {reply}")
            __env['save_log'](user_input, reply)
            __env['ui_emit']('SAY', reply, emotion='soft_smile')
        except Exception:
            print(f"{__env['NOAH_NAME']}：今は少し不安定みたいだ。")
