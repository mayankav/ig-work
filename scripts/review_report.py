"""Complete owner issue reports; no discarded issues or invented progress."""
import html


def caption(token, manual=False):
    silence = ('⏸ No reply: stays held. Your approval accepts the reported claim concerns.' if manual else
               '⏰ No reply: posts one hour after the complete report arrives.')
    return (f'🫏 CAROUSEL REVIEW\nReview ID: {token}\n\n'
            'Steps [######----] 3/5\nBuilt → checked → rendered → decision → posted\n\n'
            'Read the issue report below. One reply decides the whole carousel.\n\n'
            f'{silence}\nA redo stops this timer. A new preview gets a new decision.')


def pages(token, checked, base):
    names = {'H3_FALSE_PSYCH':'Claim not supported by the source','H5_ABSOLUTE_PROMISE':'Promises a result','H6_SHAME':'Tone may blame the reader','H7_INCOHERENT':'Slides do not connect clearly','H8_VOICE':'Wording needs review'}
    issues = []
    for item in checked.get('objections', []):
        issues.append(f"Slide {item.get('slide', '?')} · {names.get(item.get('category'), 'Content review note')}\n"
                      f"Text: {item.get('quote', '(no quoted text)')}\nConcern: {item.get('why', '')}")
    issues.extend(str(note) for note in checked.get('style_notes', []))
    # Exact duplicates may be combined; every distinct finding remains present.
    issues = list(dict.fromkeys(issues))
    silence = ('⏸ NO REPLY: this carousel stays paused until you decide.' if checked.get('outcome') == 'owner_review' else '⏰ NO REPLY: publish one hour after all review messages arrive, then send the Instagram link here.')
    blocks = [silence, f'📋 ALL DETECTED ISSUES · {len(issues)}\n'
              'These are check findings, not proof that a claim is false. Image checks may miss visible defects.']
    blocks += [f'⚠️ {n}. {issue}' for n, issue in enumerate(issues, 1)]
    if not issues: blocks += ['✅ No issues reported by the completed checks.']
    blocks += [f'📎 Caption: {base}/caption.txt\n📎 Full notes: {base}/review_notes.txt']
    blocks += [f'💬 CHOOSE ONE REPLY\n'
               f'approve {token}\nPublish this exact version; accept all listed issues.\n\n'
               f'disapprove {token}\nCancel only this carousel. Future posts continue.\n\n'
               f'redo {token} all\nNew concept, text and carousel.\n\n'
               f'redo {token} images 2,4,7\nNew images for those slides; keep all text and other images.\n\n'
               f'redo {token} images all\nNew images for all nine slides; keep the text.\n\n'
               'Use unique slide numbers 1–9, separated by commas. No ranges or mixed actions. '
               'To reply: copy one command above, change only the slide numbers if needed, and send it in this chat. You may also use Telegram Reply on a review message and omit its ID. Text problems need full redo; image redo does not fix words. '
               'Old review IDs cannot change a replacement. Once upload starts, a reply cannot cancel it. '
               'If redo fails or quota is too low, the carousel stays held. No partial replacement posts.']
    # Split before escaping, preserving every character even for one huge issue.
    chunks, current = [], ''
    for block in blocks:
        for start in range(0, len(block), 1800):
            part = html.escape(block[start:start+1800])
            # Escaping can expand a pathological quote sixfold. Bound by escaped length.
            # Such a report is sent as plain visible entities rather than broken HTML.
            if len(part) > 3000:
                part = block[start:start+1800]
                for char in part:
                    encoded = html.escape(char)
                    if len(current)+len(encoded)>3000: chunks.append(current); current=''
                    current += encoded
                continue
            if len(current)+len(part)+2>3000: chunks.append(current); current=''
            current += ('\n\n' if current else '') + part
    if current: chunks.append(current)
    commands = [f'approve {token}', f'disapprove {token}', f'redo {token} all', f'redo {token} images 2,4,7', f'redo {token} images all']
    for i, chunk in enumerate(chunks):
        for command in commands:
            chunk = chunk.replace('\n'+command+'\n', '\n<code>'+command+'</code>\n')
        chunks[i] = chunk
    return [f'<b>🫏 REVIEW · {n}/{len(chunks)}</b>\nReview ID: {token}\n\n{body}' for n, body in enumerate(chunks, 1)]
