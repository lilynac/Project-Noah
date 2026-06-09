# Split-out implementation from Noah.py.

def initiative_loop(stop_event, runtime=None):
    __env = runtime if runtime is not None else {}
    '\n    initiative 自発発話ループ（D2/D4の観測点）\n    - ループ開始/生存をログで可視化\n    - should_fire_initiative の precheck で止まった理由も必ずログ化\n    '
    logger = __env['_get_logger']()
    logger.info('INITIATIVE_LOOP_START')
    initial_wait = __env['random'].uniform(20, 60)
    end_at = __env['time'].time() + initial_wait
    while __env['time'].time() < end_at:
        if stop_event is not None and stop_event.wait(0.2):
            logger.info('INITIATIVE_LOOP_STOP')
            return
    while True:
        if stop_event is not None and stop_event.is_set():
            try:
                __env['_get_logger']().info('INITIATIVE_LOOP_STOP')
            except Exception:
                pass
            return
        try:
            delay = __env['_next_initiative_delay']()
            logger.info(f'INITIATIVE_LOOP_TICK ns=initiative delay={delay:.1f}')
            logger.info('INITIATIVE_TICK_FLOW ns=initiative reached_after_tick_log')
            if __env['DEBUG_INITIATIVE_LOOP']:
                logger.info(f'INITIATIVE_LOOP_TICK delay={delay:.1f}')
            if stop_event is not None and stop_event.wait(delay):
                logger.info('INITIATIVE_LOOP_STOP')
                return
            if __env['DEBUG_INITIATIVE_LOOP']:
                logger.info('INITIATIVE_LOOP_TICK reached')
            now = __env['time'].time()
            logger.info('INITIATIVE_MEMORY_POINT ns=initiative before_retrieve')
            if __env['DecisionEngine'] is None or __env['load_signals'] is None:
                ok, reason = __env['should_fire_initiative'](now)
                if not ok:
                    __env['log_initiative_gate'](now, reason, '(precheck)')
                    if reason in ('muted', 'conversation_active', 'ipc_busy', 'suppressed'):
                        __env['set_initiative_state']('OFF', reason)
                    if reason == 'muted':
                        if stop_event is not None and stop_event.wait(5):
                            logger.info('INITIATIVE_LOOP_STOP')
                            return
                    continue
                __env['set_initiative_state']('ON', 'ready')
            else:
                ini = __env['load_signals']()
                try:
                    sup = __env['_sup_load'](__env['SUPPRESSION_PATH'])
                    persistent = __env['_sup_is_suppressed'](sup)
                    logger.info(f'SUPPRESSION_STATE ns=dialogue persistent={persistent}')
                except Exception:
                    persistent = False
                    logger.info('SUPPRESSION_STATE ns=dialogue persistent=False err=load_failed')
                recent_turns = __env['_recent_turn_texts']()
                memory_ctx = None
                try:
                    from src.memory.retrieve import retrieve_memories
                    q = ' '.join([t for t in recent_turns or [] if t][-3:]).strip() or 'recent'
                    mem = __env['retrieve_memories'](q, top_narrative=2, top_summary=3, top_episode=0)
                    memory_ctx = {'narrative': mem.get('narrative') or [], 'summary': mem.get('summary') or []}
                    logger.info('INITIATIVE_MEMORY_CTX ns=initiative n=%d s=%d', len((memory_ctx or {}).get('narrative') or []), len((memory_ctx or {}).get('summary') or []))
                except Exception as e:
                    __env['log_error']('INITIATIVE_MEMORY_RETRIEVE', e, {})
                state = __env['load_state_snippet']()
                eng = __env['DecisionEngine']()
                dec = eng.evaluate(ini, now_ts=now, persistent_suppressed=persistent, recent_turns=recent_turns, memory_ctx=memory_ctx, affective_state=state)
                try:
                    logger.info(f"INITIATIVE_EVAL ns=initiative opp={dec.debug.get('opportunity', {})} val={dec.debug.get('value', {})} sup={dec.debug.get('suppression', {})} final={dec.debug.get('final_score')} thr={dec.debug.get('threshold')} speak={dec.speak} cooldown={dec.cooldown_sec}")
                except Exception:
                    pass
                if not dec.speak:
                    __env['set_initiative_state']('OFF', 'decision')
                    if stop_event is not None and stop_event.wait(dec.cooldown_sec):
                        logger.info('INITIATIVE_LOOP_STOP')
                        return
                    continue
                __env['set_initiative_state']('ON', 'ready')
            with __env['_state_lock']:
                __env['_initiative_count'] += 1
            style = 'micro'
            try:
                style = (dec.debug.get('value') or {}).get('style') or 'micro'
            except Exception:
                pass
            try:
                state
            except NameError:
                state = __env['load_state_snippet']()
            today = __env['datetime'].now().date()
            research_phrase = __env['build_research_phrase'](research_path=__env['NOAH_RESEARCH_PATH'], now_date=today, initiative_count=__env['_initiative_count'], injected_today=__env['_research_injected_today'], last_injected_date=__env['_last_research_injected_date'], is_work_mode=__env['is_work_mode'](), daily_cap=2, every_n=5)
            gen = __env['generate_initiative_text'](style=style, signals=ini, recent_turns=recent_turns, state_snippet=state, research_phrase=research_phrase, llm_client=__env['client'], model='gpt-4o-mini', memory_ctx=memory_ctx)
            text = gen.text
            if __env['_initiative_is_duplicate'](text):
                base_seed = int(now) ^ __env['_initiative_count'] * 131
                text_alt = None
                for i in range(2):
                    gen2 = __env['generate_initiative_text'](style=style, signals=ini, recent_turns=recent_turns, state_snippet=state, research_phrase=research_phrase, seed=base_seed + i + 1, llm_client=__env['client'], model='gpt-4o-mini', memory_ctx=memory_ctx)
                    if not __env['_initiative_is_duplicate'](gen2.text):
                        text_alt = gen2.text
                        break
                if not text_alt:
                    __env['set_initiative_state']('OFF', 'dup_skip')
                    continue
                text = text_alt
            if not __env['emit_initiative'](text):
                continue
            try:
                if __env['touch_noah_message'] and __env['save_signals']:
                    __env['touch_noah_message'](ini, now_ts=__env['time'].time(), is_initiative=True)
                    __env['save_signals'](ini)
            except Exception:
                pass
            with __env['_state_lock']:
                __env['_last_noah_initiative_at'] = __env['time'].time()
        except Exception as e:
            __env['log_error']('INITIATIVE_LOOP', e, {})
            with __env['_state_lock']:
                __env['_last_noah_initiative_at'] = __env['time'].time()
            if stop_event is not None and stop_event.wait(2.0):
                logger.info('INITIATIVE_LOOP_STOP')
                return
            continue
