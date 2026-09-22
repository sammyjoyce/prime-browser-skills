"""Local-browser freshness/execution regressions. No model calls or external websites."""

from urllib.parse import quote

from jev_ultrafast.browser import Browser, StalePage

HTML = """<!doctype html><title>Guard checks</title>
<style>body{margin:30px}button{width:180px;height:50px}#outside{position:absolute;top:3000px}</style>
<p id="context">Cart total: $10</p>
<button id="target" onclick="window.clicks=(window.clicks||0)+1">Continue</button>
<label>City<input id="field" value="Zurich"></label>
<label><input id="toggle" type="checkbox">Refundable</label>
<select aria-label="Category"><option>All</option><option>Design</option></select>
<p id="outside">Unrelated offscreen text</p>"""


def main():
    browser = Browser("data:text/html," + quote(HTML))
    passed = []
    try:
        page = browser.observe(screenshot=False)
        action = next(a for a in page["actions"] if a["label"] == "Continue")
        browser.evaluate("document.querySelector('#target').style.transform='translateX(200px)'")
        assert browser.fresh(page), "Movement should use fresh geometry, not another model call"
        browser.act(action, page)
        assert browser.evaluate("window.clicks") == 1
        passed.append("moving target clicked at its current location")

        browser.evaluate("document.querySelector('#outside').textContent='Updated outside the viewport'")
        assert browser.fresh(page)
        passed.append("unrelated offscreen text does not invalidate")

        mutations = {
            "visible context": "document.querySelector('#context').textContent='Cart total: $100'",
            "accessible label": "document.querySelector('#target').setAttribute('aria-label','Delete account')",
            "field property": "document.querySelector('#field').value='London'",
            "checkbox property": "document.querySelector('#toggle').checked=true",
            "disabled target": "document.querySelector('#target').disabled=true",
            "read-only field": "document.querySelector('#field').readOnly=true",
            "hidden target": "document.querySelector('#target').style.display='none'",
            "replaced node": "document.querySelector('#target').outerHTML=document.querySelector('#target').outerHTML",
            "dropdown option": "document.querySelector('select').options[1].text='Coastal'",
        }
        for label, expression in mutations.items():
            browser.evaluate("document.querySelector('#target').style.display='block'; "
                             "document.querySelector('#target').disabled=false")
            page = browser.observe(screenshot=False)
            browser.evaluate(expression)
            assert not browser.fresh(page), label
            passed.append(label + " invalidates")

        browser.evaluate("document.querySelector('#target').disabled=false; "
                         "document.querySelector('#target').style.display='block'")
        page = browser.observe(screenshot=False)
        action = next(a for a in page["actions"] if a["label"] == "Delete account")
        # A textless overlay does not alter the model's semantic state, but must block a click.
        browser.evaluate("const cover=document.createElement('div'); "
                         "cover.style.cssText='position:fixed;inset:0;z-index:9999;background:white'; "
                         "document.body.append(cover)")
        assert browser.fresh(page)
        try:
            browser.act(action, page)
        except (RuntimeError, StalePage):
            pass
        else:
            raise AssertionError("Covered target was clicked")
        assert browser.evaluate("window.clicks") == 1
        passed.append("overlay blocked before input")

        browser.evaluate("document.body.innerHTML=" + repr("""
          <form><p id="price">Total $10</p>
          <button type="button" id="buy">Buy</button>
          <label>Search <input id="query" role="combobox" aria-controls="suggestions"></label>
          <div role="listbox" id="suggestions"></div>
          <label><input id="check" type="checkbox">Enabled</label>
          <label><input id="radio" type="radio">Choice</label>
          <input id="readonly" aria-label="Read only" readonly>
          <input id="secret" type="password" value="never expose this">
          <button id="off" disabled>Disabled</button>
          <select id="category" aria-label="Category">
            <option>All</option><option>Design</option><option disabled>Unavailable</option>
          </select></form><aside id="unrelated">News</aside>
        """))
        page = browser.observe(screenshot=False)
        buy = next(a for a in page["actions"] if a["label"] == "Buy")
        browser.evaluate("document.querySelector('#unrelated').textContent='New unrelated news'")
        assert browser.fresh(page, buy)
        assert not browser.fresh(page)
        passed.append("click guard accepts unrelated visible updates; terminal guard rejects them")
        for label, expression in {
            "nearby price": "document.querySelector('#price').textContent='Total $100'",
            "form value": "document.querySelector('#query').value='changed'",
            "form toggle": "document.querySelector('#check').checked=true",
            "target replacement": "document.querySelector('#buy').outerHTML=document.querySelector('#buy').outerHTML",
        }.items():
            page = browser.observe(screenshot=False)
            buy = next(a for a in page["actions"] if a["label"] == "Buy")
            browser.evaluate(expression)
            assert not browser.fresh(page, buy), label
            passed.append(label + " invalidates action-specific guard")

        page = browser.observe(screenshot=False)
        actions = page["actions"]
        for role in ("checkbox", "radio"):
            assert {a["kind"] for a in actions if a.get("role") == role} == {"click"}
        assert {a["kind"] for a in actions if a["label"] == "Read only"} == {"click"}
        assert not any(a["label"] == "Disabled" or a.get("value") == "never expose this" for a in actions)
        assert [a["value"] for a in actions if a["kind"] == "select"] == ["Design"]
        passed.append("native controls expose only supported operations and safe values")

        select = next(a for a in actions if a["kind"] == "select")
        browser.act(select, page)
        assert browser.evaluate("document.querySelector('#category').value") == "Design"
        passed.append("native dropdown selects an observed option")

        browser.evaluate("document.querySelector('#query').addEventListener('input',()=>setTimeout(()=>{"
                         "document.querySelector('#suggestions').innerHTML='<div role=option>Generated</div>'"
                         "},60))")
        page = browser.observe(screenshot=False)
        field = next(a for a in page["actions"] if a["kind"] == "fill")
        browser.act(field, page, text="Generated")
        page = browser.observe(screenshot=False)
        value = browser.evaluate("document.querySelector('#query').value")
        assert value == "Generated", repr(value)
        assert any(a.get("role") == "option" for a in page["actions"])
        passed.append("real text input waits for asynchronous combobox suggestions")

        browser.evaluate("window.inputEvents=0; document.querySelector('#query')"
                         ".addEventListener('input',()=>{window.inputEvents++})")
        page = browser.observe(screenshot=False)
        field = next(a for a in page["actions"] if a["kind"] == "fill")
        # An empty supplied value means "clear this field", so it must really empty it.
        browser.act(field, page, text="")
        page = browser.observe(screenshot=False)
        value = browser.evaluate("document.querySelector('#query').value")
        assert value == "", repr(value)
        events = browser.evaluate("window.inputEvents")
        assert events >= 1, repr(events)
        assert next(a for a in page["actions"] if a["kind"] == "fill")["value"] == ""
        passed.append("an empty value clears the field and fires a real input event")

        tiny = "font-size:1px;line-height:1px;word-break:break-all;margin:0"
        browser.evaluate("document.body.innerHTML=" + repr(f'<p style="{tiny}">{"a" * 20}</p>'))
        page = browser.observe(screenshot=False)
        assert page["text_truncated"] is False, repr(page.get("text_truncated"))
        assert len(page["text"]) == 20
        passed.append("20 visible characters are not truncated")

        browser.evaluate("document.body.innerHTML=" + repr(f'<p style="{tiny}">{"b" * 6000}</p>'))
        page = browser.observe(screenshot=False)
        assert page["text_truncated"] is False, "exactly 6000 visible characters is not truncated"
        assert len(page["text"]) == 6000
        passed.append("exactly 6000 visible characters is not truncated")

        browser.evaluate("document.body.innerHTML=" + repr(f'<p style="{tiny}">{"c" * 7000}</p>'))
        page = browser.observe(screenshot=False)
        assert page["text_truncated"] is True
        assert len(page["text"]) == 6000
        passed.append("7000 visible characters set text_truncated and cap text at 6000")

        browser.evaluate(
            "document.body.innerHTML="
            + repr(f'<p style="{tiny}">{"d" * 6000}</p><p style="{tiny}">more</p>')
        )
        page = browser.observe(screenshot=False)
        assert page["text_truncated"] is True
        assert len(page["text"]) == 6000
        passed.append("an extra in-view text node after 6000 sets text_truncated")

        browser.evaluate(
            "document.body.innerHTML="
            + repr(
                f'<p style="{tiny}">{"e" * 6000}</p>'
                '<p style="display:none">hidden trailing visible-looking text</p>'
                "<p hidden>also hidden</p>"
            )
        )
        page = browser.observe(screenshot=False)
        assert page["text_truncated"] is False, "hidden trailing nodes must not set text_truncated"
        assert len(page["text"]) == 6000
        passed.append("hidden trailing nodes do not set text_truncated")

        buttons = "".join(
            f'<button class="g" style="left:{16 * (i % 60)}px;top:{16 * (i // 60)}px">{i}</button>'
            for i in range(251)
        )
        browser.evaluate(
            "document.body.innerHTML="
            + repr(
                '<style>button.g{position:absolute;width:14px!important;height:14px!important;'
                "padding:0;margin:0;font-size:8px;border:0}</style>"
                f'<div style="position:relative;width:1000px;height:90px">{buttons}</div>'
            )
        )
        page = browser.observe(screenshot=False)
        element_actions = [a for a in page["actions"] if str(a.get("id", "")).startswith("e")]
        waits = [a for a in page["actions"] if a.get("id") == "wait"]
        scrolls = [a for a in page["actions"] if a.get("kind") == "scroll"]
        assert page["omitted_actions"] == 1, page["omitted_actions"]
        assert len(element_actions) == 250, len(element_actions)
        assert len(waits) == 1
        assert len(page["actions"]) == 250 + len(waits) + len(scrolls)
        passed.append(
            f"251 in-view controls: omitted_actions=1 capped=250 wait={len(waits)} scroll={len(scrolls)}"
        )

        browser.evaluate("document.body.innerHTML=" + repr('<label>Search <input id="query" value="keep"></label>'))
        page = browser.observe(screenshot=False)
        field = next(a for a in page["actions"] if a["kind"] == "fill")

        browser.call("Page.navigate", url="about:blank")
        assert not browser.fresh(page, field)
        passed.append("navigation invalidates the old document")
    finally:
        browser.close()
    print("\n".join(passed))
    print(f"PASS: {len(passed)} browser guard checks; no model calls")


if __name__ == "__main__":
    main()
