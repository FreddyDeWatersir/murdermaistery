# ruff: noqa: E501 - a translation table reads better one entry to a line
"""The page in French and Italian (D-209).

The page is one HTML string with its script inside (`web.PAGE`), English
throughout. A room whose case is in another language gets a copy with its
words swapped, made once per language and kept:

- **Literals.** Every string literal in the script whose text is in the
  table below is replaced, quote for quote, by its translation. Only string
  literals are touched, never the code around them, so a translation cannot
  break the script; the scanner skips comments and regular expressions.
- **Snippets.** A few places build a word out of pieces ("question" + "s"),
  which no table of literals can translate. Those few lines are swapped
  whole.

A string missing from the table stays English, which is the failure you want:
visible, harmless. `tests/test_i18n.py` fails when a key here no longer exists
in the page, so the table cannot quietly rot when the page changes.

The tables are plain text on purpose: edit a translation here and the page
changes on the next restart.
"""

from __future__ import annotations

import re
from functools import cache

# --------------------------------------------------------------------------
# Script literals: English text exactly as it is between the quotes.
# --------------------------------------------------------------------------

LITERALS: dict[str, dict[str, str]] = {
    "it": {
        "You have not asked ": "Non hai ancora chiesto nulla a ",
        " anything yet.": ".",
        " earlier</em>": " prima</em>",
        '<span class="label">You have</span>': '<span class="label">Hai con te</span>',
        " — from ": " — da ",
        "<i>from ": "<i>da ",
        " has seen it</small>": " l'ha visto</small>",
        '<span class="asked">You put ': '<span class="asked">Metti ',
        " in front of ": " davanti a ",
        '<span class="body">They look at it. Ask them.</span>':
            '<span class="body">Lo guardano. Chiedi pure.</span>',
        '<div class="ftab">CASE FILE</div><div class="stamp">CONFIDENTIAL</div>':
            '<div class="ftab">FASCICOLO</div><div class="stamp">RISERVATO</div>',
        '<div class="fileno">FILE No. ': '<div class="fileno">FASCICOLO N. ',
        '" alt=""><span>Exhibit A</span></div>': '" alt=""><span>Reperto A</span></div>',
        "<h4>1 &middot; What happened</h4>": "<h4>1 &middot; Cosa è successo</h4>",
        "</b> is dead. ": "</b> non è più in vita. ",
        " found the body in the ": " ha trovato il corpo in ",
        "<p>Last seen alive: <b>": "<p>Visto vivo l'ultima volta: <b>",
        "</b>, in the ": "</b>, in ",
        ". When it happened after that, nobody says.</p>":
            ". Quando sia successo dopo, nessuno lo dice.</p>",
        '<div class="asked"><b>Found with the body</b><ul>':
            '<div class="asked"><b>Trovato accanto al corpo</b><ul>',
        "</b> is dead, and one of the people here did it.</p>":
            "</b> non è più in vita, e il colpevole è uno dei presenti.</p>",
        '<div class="asked"><b>What you were asked for</b><p>':
            '<div class="asked"><b>Che cosa ti hanno chiesto</b><p>',
        "You are <b>": "Tu sei <b>",
        "You arrived after that. ": "Arrivi dopo i fatti. ",
        "You saw none of it, and everything you are about to be told, you are being told.</p>":
            "Non hai visto nulla, e tutto quello che sentirai ti viene raccontato.</p>",
        '<h4>2 &middot; Persons present</h4><div class="persons">':
            '<h4>2 &middot; Persone presenti</h4><div class="persons">',
        "<h4>3 &middot; What everybody knows</h4><ul>": "<h4>3 &middot; Quello che sanno tutti</h4><ul>",
        " &middot; You</h4><p>": " &middot; Tu</h4><p>",
        " are on the road. You have about <b>": " sono in viaggio. Hai circa <b>",
        "</b> questions before they are at the door.</p>":
            "</b> domande prima che bussino alla porta.</p>",
        '<button class="go" id="briefgo">Open the case</button>':
            '<button class="go" id="briefgo">Apri il caso</button>',
        "<h3>How to play</h3>": "<h3>Come si gioca</h3>",
        "<p>Somebody in this house killed ": "<p>Qualcuno in questa casa ha ucciso ",
        "the victim": "la vittima",
        ". You have a ": ". Hai un ",
        "limited number of questions before ": "numero limitato di domande prima che arrivino ",
        " arrive. Find out who, and why.</p>": ". Scopri chi è stato, e perché.</p>",
        "<h4>Asking</h4><ul>": "<h4>Fare domande</h4><ul>",
        "<li>Pick a person along the bottom and ask anything, in plain words. They answer ":
            "<li>Scegli una persona in basso e chiedi quello che vuoi, a parole tue. "
            "Rispondono ",
        "as themselves: they evade, they lie about where they were, they get rattled.</li>":
            "come sé stessi: svicolano, mentono su dove erano, si agitano.</li>",
        "<li>People give things up when you know enough to press them, or when you show them ":
            "<li>Le persone cedono quando sai abbastanza da incalzarle, o quando mostri "
            "loro ",
        "something. Objects you come across appear under the cast; click one to put it in ":
            "qualcosa. Gli oggetti che trovi compaiono sotto i personaggi: cliccane uno per "
            "metterlo ",
        "front of whoever you are talking to.</li>": "davanti a chi stai interrogando.</li>",
        "<li>Every question counts down the clock in the corner.</li></ul>":
            "<li>Ogni domanda fa scorrere l'orologio nell'angolo.</li></ul>",
        "<h4>The notebook</h4><ul>": "<h4>Il taccuino</h4><ul>",
        "<li><b>Transcript</b>: one page per person, with what they have given up at the top, ":
            "<li><b>Verbale</b>: una pagina per persona, con in cima ciò che hanno ammesso, ",
        "everything they said, and your own notes. Search finds a word across everybody. ":
            "tutto quello che hanno detto e i tuoi appunti. La ricerca trova una parola in "
            "tutti i verbali. ",
        "Select words to underline them; click an underline to rub it out.</li>":
            "Seleziona delle parole per sottolinearle; clicca una sottolineatura per "
            "cancellarla.</li>",
        "<li><b>Map</b>: the building, and where people say everybody was, hour by hour. Red ":
            "<li><b>Mappa</b>: l'edificio, e dove dicono che fossero tutti, ora per ora. "
            "Il rosso ",
        "means two people put somebody in different rooms at the same hour. A ringed tag was ":
            "vuol dire che due persone mettono qualcuno in stanze diverse alla stessa ora. "
            "Un'etichetta cerchiata è stata ",
        "confirmed by somebody else. Your pencil puts anyone anywhere, dashed, so you can ":
            "confermata da qualcun altro. La tua matita mette chiunque ovunque, tratteggiato, "
            "così puoi ",
        "try a theory without mistaking it for testimony.</li></ul>":
            "provare un'ipotesi senza scambiarla per una testimonianza.</li></ul>",
        "<h4>Ending it</h4><ul>": "<h4>Chiudere il caso</h4><ul>",
        "<li>When you are ready, press <b>Accuse</b>, name who did it and say why. You can do ":
            "<li>Quando vuoi, premi <b>Accusa</b>, indica il colpevole e di' perché. "
            "Puoi farlo ",
        "this even after the questions run out.</li>": "anche dopo aver finito le domande.</li>",
        "<li>The <b>Case file</b> button brings back everything you were told on arrival.</li></ul>":
            "<li>Il pulsante <b>Fascicolo</b> riporta tutto ciò che ti hanno detto al tuo "
            "arrivo.</li></ul>",
        '<button class="close" id="helpclose">Back to the case</button>':
            '<button class="close" id="helpclose">Torna al caso</button>',
        " is dead. ": " non è più in vita. ",
        " is dead. One of them did it.": " non è più in vita. È stato uno di loro.",
        " You are ": " Tu sei ",
        " are on their way, and you are not ": " stanno arrivando, e tu non sei ",
        "Sound on": "Audio sì",
        "Sound off": "Audio no",
        '<span class="body">You do not get to ask it. There are cars on the ':
            '<span class="body">Non fai in tempo a chiederlo. Ci sono auto sulla ',
        "gravel and somebody is already at the door. Whatever you think you ":
            "ghiaia e qualcuno è già alla porta. Quello che pensi di ",
        "know, you know it now.</span>": "sapere, lo sai adesso.</span>",
        "(no answer came back)": "(nessuna risposta)",
        " are here": " sono qui",
        " are here. You can still name somebody.": " sono qui. Puoi ancora fare un nome.",
        "Transcript": "Verbale",
        "Map": "Mappa",
        "they told you": "te l'ha detto",
        " told you": " te l'ha detto",
        "<h4>Given up</h4>": "<h4>Ammesso</h4>",
        '<div class="item cold">Refused to answer ': '<div class="item cold">Non ha risposto ',
        "<h4>What they said</h4></div>": "<h4>Cosa ha detto</h4></div>",
        "<h2>Everything anybody said about it</h2>": "<h2>Tutto quello che è stato detto</h2>",
        "Nothing matches that.": "Nessun risultato.",
        "You have not asked them anything yet.": "Nessuna domanda, per ora.",
        '<div class="empty hint">Select words to underline them. Click an underline to rub it out.</div>':
            '<div class="empty hint">Seleziona delle parole per sottolinearle. Clicca una '
            "sottolineatura per cancellarla.</div>",
        "<h2>Your notes on ": "<h2>I tuoi appunti su ",
        '" rows="5" placeholder="What you make ': '" rows="5" placeholder="Che idea ti sei fatto ',
        "of them, what to come back to…\">": "di loro, su cosa tornare…\">",
        "your pencil": "la tua matita",
        ", from ": ", da ",
        "<h2>The building</h2>": "<h2>L'edificio</h2>",
        '<div class="empty" style="margin:2px 0 0">Nobody has placed ':
            '<div class="empty" style="margin:2px 0 0">Nessuno ha collocato ',
        " at this hour.</div>": " a quest'ora.</div>",
        '<div class="empty" style="margin:6px 0 18px">A break in a wall is a door. ':
            '<div class="empty" style="margin:6px 0 18px">Un varco nel muro è una porta. ',
        "Red means two ": "Il rosso vuol dire che due ",
        "people put them in different rooms at this hour, and a ringed tag was ":
            "persone li mettono in stanze diverse a quest'ora, e un'etichetta cerchiata è "
            "stata ",
        "confirmed by somebody other than themselves.": "confermata da qualcuno che non è lui stesso.",
        " Click a room to stand in it.": " Clicca una stanza per entrarci.",
        '<h2>Your pencil</h2><div id="pencilbar">': '<h2>La tua matita</h2><div id="pencilbar">',
        "Click a cell below, or a room on the plan, to pencil ":
            "Clicca una casella qui sotto, o una stanza sulla pianta, per segnare a matita ",
        " in at that hour. Click again to rub ": " a quell'ora. Clicca di nuovo per ",
        "it out, or pick them again to put the pencil down.":
            "cancellare, o sceglilo di nuovo per posare la matita.",
        "Pick somebody to pencil them in yourself, the victim included. Your marks are ":
            "Scegli qualcuno da segnare tu stesso, vittima compresa. I tuoi segni sono ",
        "dashed: a guess, not testimony.": "tratteggiati: un'ipotesi, non una testimonianza.",
        '<h2>Where they say they were</h2><div class="tlwrap"><table class="tl">':
            '<h2>Dove dicono di essere stati</h2><div class="tlwrap"><table class="tl">',
        ", your pencil": ", la tua matita",
        '<span><b>?</b>unaccounted for</span></div>': '<span><b>?</b>non si sa dove</span></div>',
        " (the deceased)": " (la vittima)",
        '<div class="empty" style="margin-top:12px">Only what somebody has ':
            '<div class="empty" style="margin-top:12px">Solo ciò che qualcuno ti ha ',
        "told you. Red means two people put them in different rooms at that hour. ":
            "detto. Il rosso vuol dire che due persone li mettono in stanze diverse a "
            "quell'ora. ",
        "The bottom row is where your questions have not reached. A ringed tag was ":
            "L'ultima riga è dove le tue domande non sono arrivate. Un'etichetta cerchiata "
            "è stata ",
        "<h3>Charge ": "<h3>Accusa ",
        "<p>In your own words: what did they do it for? Nothing here is marked. ":
            "<p>A parole tue: perché l'ha fatto? Qui niente viene corretto. ",
        "You will see the whole case afterwards and can judge your own answer ":
            "Dopo vedrai tutto il caso e potrai giudicare da solo la tua risposta ",
        "against it. This ends the game.</p>": "confrontandola. Così la partita finisce.</p>",
        '<button id="press" class="accuse">Charge ': '<button id="press" class="accuse">Accusa ',
        '<button id="backout">Not yet</button></div>': '<button id="backout">Non ancora</button></div>',
        '<div class="said">You charged ': '<div class="said">Hai accusato ',
        "You named him.": "Hai fatto il nome giusto.",
        "Wrong.": "Sbagliato.",
        '<div class="who">The killer was <b>': '<div class="who">Il colpevole era <b>',
        " asked</div></div>": "</div></div>",
        '<div class="act"><h2>The reason</h2>': '<div class="act"><h2>Il movente</h2>',
        '<div class="item soft"><span class="tag">what you wrote</span>':
            '<div class="item soft"><span class="tag">cosa hai scritto</span>',
        '"><span class="tag">what it was</span>': '"><span class="tag">com\'era davvero</span>',
        '<p class="empty">Nobody is marking this. Read the ':
            '<p class="empty">Nessuno lo corregge. Leggi le ',
        "two and decide whether you had it.</p>": "due e decidi se ci avevi visto giusto.</p>",
        '<div class="act"><h2>What was not true</h2>': '<div class="act"><h2>Cosa non era vero</h2>',
        "</b> said the ": "</b> ha detto ",
        ". They were in the ": ". In realtà era in ",
        '<br><span class="empty">Covering: ': '<br><span class="empty">Per coprire: ',
        '<div class="act"><h2>Who could have broken it</h2>':
            '<div class="act"><h2>Chi avrebbe potuto smentirlo</h2>',
        "you never asked them": "nessuna domanda",
        '<div class="act"><h2>What you got out of them': '<div class="act"><h2>Cosa hai ottenuto',
        '<div class="act"><h2>Secrets you never found</h2>':
            '<div class="act"><h2>Segreti che non hai trovato</h2>',
        "the police": "gli agenti",
        "from ": "da ",
        " at ": " alle ",
        "asked ": "chiesto ",
    },
    "fr": {
        "You have not asked ": "Vous n'avez encore rien demandé à ",
        " anything yet.": ".",
        " earlier</em>": " plus tôt</em>",
        '<span class="label">You have</span>': '<span class="label">Vous avez</span>',
        " — from ": " — de ",
        "<i>from ": "<i>de ",
        " has seen it</small>": " l'a vu</small>",
        '<span class="asked">You put ': '<span class="asked">Vous posez ',
        " in front of ": " devant ",
        '<span class="body">They look at it. Ask them.</span>':
            '<span class="body">On le regarde. Posez votre question.</span>',
        '<div class="ftab">CASE FILE</div><div class="stamp">CONFIDENTIAL</div>':
            '<div class="ftab">DOSSIER</div><div class="stamp">CONFIDENTIEL</div>',
        '<div class="fileno">FILE No. ': '<div class="fileno">DOSSIER N° ',
        '" alt=""><span>Exhibit A</span></div>': '" alt=""><span>Pièce A</span></div>',
        "<h4>1 &middot; What happened</h4>": "<h4>1 &middot; Ce qui s'est passé</h4>",
        "</b> is dead. ": "</b> n'est plus en vie. ",
        " found the body in the ": " a trouvé le corps dans ",
        "<p>Last seen alive: <b>": "<p>Vu vivant pour la dernière fois : <b>",
        "</b>, in the ": "</b>, dans ",
        ". When it happened after that, nobody says.</p>":
            ". Quand c'est arrivé ensuite, personne ne le dit.</p>",
        '<div class="asked"><b>Found with the body</b><ul>':
            '<div class="asked"><b>Trouvé près du corps</b><ul>',
        "</b> is dead, and one of the people here did it.</p>":
            "</b> n'est plus en vie, et le coupable est l'une des personnes présentes.</p>",
        '<div class="asked"><b>What you were asked for</b><p>':
            '<div class="asked"><b>Ce qu\'on vous a demandé</b><p>',
        "You are <b>": "Vous êtes <b>",
        "You arrived after that. ": "Vous arrivez après les faits. ",
        "You saw none of it, and everything you are about to be told, you are being told.</p>":
            "Vous n'avez rien vu, et tout ce que vous allez entendre, on vous le raconte.</p>",
        '<h4>2 &middot; Persons present</h4><div class="persons">':
            '<h4>2 &middot; Personnes présentes</h4><div class="persons">',
        "<h4>3 &middot; What everybody knows</h4><ul>": "<h4>3 &middot; Ce que tout le monde sait</h4><ul>",
        " &middot; You</h4><p>": " &middot; Vous</h4><p>",
        " are on the road. You have about <b>": " sont en route. Vous avez environ <b>",
        "</b> questions before they are at the door.</p>":
            "</b> questions avant qu'ils ne frappent à la porte.</p>",
        '<button class="go" id="briefgo">Open the case</button>':
            '<button class="go" id="briefgo">Ouvrir le dossier</button>',
        "<h3>How to play</h3>": "<h3>Comment jouer</h3>",
        "<p>Somebody in this house killed ": "<p>Quelqu'un dans cette maison a tué ",
        "the victim": "la victime",
        ". You have a ": ". Vous avez un ",
        "limited number of questions before ": "nombre limité de questions avant l'arrivée ",
        " arrive. Find out who, and why.</p>": ". Découvrez qui, et pourquoi.</p>",
        "<h4>Asking</h4><ul>": "<h4>Interroger</h4><ul>",
        "<li>Pick a person along the bottom and ask anything, in plain words. They answer ":
            "<li>Choisissez une personne en bas et demandez ce que vous voulez, avec vos "
            "mots. On vous répond ",
        "as themselves: they evade, they lie about where they were, they get rattled.</li>":
            "en personne : on esquive, on ment sur l'endroit où l'on était, on se trouble.</li>",
        "<li>People give things up when you know enough to press them, or when you show them ":
            "<li>Les gens lâchent des choses quand vous en savez assez pour insister, ou "
            "quand vous leur montrez ",
        "something. Objects you come across appear under the cast; click one to put it in ":
            "quelque chose. Les objets que vous trouvez apparaissent sous les personnages : "
            "cliquez sur l'un d'eux pour le poser ",
        "front of whoever you are talking to.</li>": "devant la personne que vous interrogez.</li>",
        "<li>Every question counts down the clock in the corner.</li></ul>":
            "<li>Chaque question fait avancer l'horloge dans le coin.</li></ul>",
        "<h4>The notebook</h4><ul>": "<h4>Le carnet</h4><ul>",
        "<li><b>Transcript</b>: one page per person, with what they have given up at the top, ":
            "<li><b>Procès-verbal</b> : une page par personne, avec en tête ce qu'elle a "
            "avoué, ",
        "everything they said, and your own notes. Search finds a word across everybody. ":
            "tout ce qu'elle a dit, et vos notes. La recherche trouve un mot chez tout le "
            "monde. ",
        "Select words to underline them; click an underline to rub it out.</li>":
            "Sélectionnez des mots pour les souligner ; cliquez sur un soulignement pour "
            "l'effacer.</li>",
        "<li><b>Map</b>: the building, and where people say everybody was, hour by hour. Red ":
            "<li><b>Plan</b> : le bâtiment, et où chacun dit que tout le monde était, heure "
            "par heure. Le rouge ",
        "means two people put somebody in different rooms at the same hour. A ringed tag was ":
            "signifie que deux personnes placent quelqu'un dans des pièces différentes à la "
            "même heure. Une étiquette cerclée a été ",
        "confirmed by somebody else. Your pencil puts anyone anywhere, dashed, so you can ":
            "confirmée par quelqu'un d'autre. Votre crayon place n'importe qui n'importe où, "
            "en pointillé, pour que vous puissiez ",
        "try a theory without mistaking it for testimony.</li></ul>":
            "essayer une théorie sans la prendre pour un témoignage.</li></ul>",
        "<h4>Ending it</h4><ul>": "<h4>Conclure</h4><ul>",
        "<li>When you are ready, press <b>Accuse</b>, name who did it and say why. You can do ":
            "<li>Quand vous voulez, appuyez sur <b>Accuser</b>, nommez le coupable et "
            "dites pourquoi. Vous pouvez le faire ",
        "this even after the questions run out.</li>": "même après avoir épuisé vos questions.</li>",
        "<li>The <b>Case file</b> button brings back everything you were told on arrival.</li></ul>":
            "<li>Le bouton <b>Dossier</b> rappelle tout ce qu'on vous a dit à votre "
            "arrivée.</li></ul>",
        '<button class="close" id="helpclose">Back to the case</button>':
            '<button class="close" id="helpclose">Retour à l\'affaire</button>',
        " is dead. ": " n'est plus en vie. ",
        " is dead. One of them did it.": " n'est plus en vie. L'un d'eux est coupable.",
        " You are ": " Vous êtes ",
        " are on their way, and you are not ": " sont en route, et vous n'êtes pas ",
        "Sound on": "Son activé",
        "Sound off": "Son coupé",
        '<span class="body">You do not get to ask it. There are cars on the ':
            '<span class="body">Vous n\'aurez pas le temps de la poser. Des voitures '
            "crissent sur le ",
        "gravel and somebody is already at the door. Whatever you think you ":
            "gravier et quelqu'un est déjà à la porte. Ce que vous pensez ",
        "know, you know it now.</span>": "savoir, vous le savez maintenant.</span>",
        "(no answer came back)": "(aucune réponse)",
        " are here": " sont là",
        " are here. You can still name somebody.": " sont là. Vous pouvez encore nommer quelqu'un.",
        "Transcript": "Procès-verbal",
        "Map": "Plan",
        "they told you": "vous l'a dit",
        " told you": " vous l'a dit",
        "<h4>Given up</h4>": "<h4>Avoué</h4>",
        '<div class="item cold">Refused to answer ': '<div class="item cold">A refusé de répondre ',
        "<h4>What they said</h4></div>": "<h4>Ce qui a été dit</h4></div>",
        "<h2>Everything anybody said about it</h2>": "<h2>Tout ce qui en a été dit</h2>",
        "Nothing matches that.": "Aucun résultat.",
        "You have not asked them anything yet.": "Vous ne lui avez encore rien demandé.",
        '<div class="empty hint">Select words to underline them. Click an underline to rub it out.</div>':
            '<div class="empty hint">Sélectionnez des mots pour les souligner. Cliquez sur '
            "un soulignement pour l'effacer.</div>",
        "<h2>Your notes on ": "<h2>Vos notes sur ",
        '" rows="5" placeholder="What you make ': '" rows="5" placeholder="Ce que vous pensez ',
        "of them, what to come back to…\">": "de cette personne, ce qu'il faut revoir…\">",
        "your pencil": "votre crayon",
        ", from ": ", de ",
        "<h2>The building</h2>": "<h2>Le bâtiment</h2>",
        '<div class="empty" style="margin:2px 0 0">Nobody has placed ':
            '<div class="empty" style="margin:2px 0 0">Personne n\'a placé ',
        " at this hour.</div>": " à cette heure.</div>",
        '<div class="empty" style="margin:6px 0 18px">A break in a wall is a door. ':
            '<div class="empty" style="margin:6px 0 18px">Une ouverture dans un mur est une '
            "porte. ",
        "Red means two ": "Le rouge signifie que deux ",
        "people put them in different rooms at this hour, and a ringed tag was ":
            "personnes les placent dans des pièces différentes à cette heure, et une "
            "étiquette cerclée a été ",
        "confirmed by somebody other than themselves.": "confirmée par quelqu'un d'autre qu'eux-mêmes.",
        " Click a room to stand in it.": " Cliquez sur une pièce pour y entrer.",
        '<h2>Your pencil</h2><div id="pencilbar">': '<h2>Votre crayon</h2><div id="pencilbar">',
        "Click a cell below, or a room on the plan, to pencil ":
            "Cliquez sur une case ci-dessous, ou sur une pièce du plan, pour placer au crayon ",
        " in at that hour. Click again to rub ": " à cette heure. Cliquez à nouveau pour ",
        "it out, or pick them again to put the pencil down.":
            "l'effacer, ou choisissez-le à nouveau pour poser le crayon.",
        "Pick somebody to pencil them in yourself, the victim included. Your marks are ":
            "Choisissez quelqu'un à placer vous-même, la victime comprise. Vos marques sont ",
        "dashed: a guess, not testimony.": "en pointillé : une supposition, pas un témoignage.",
        '<h2>Where they say they were</h2><div class="tlwrap"><table class="tl">':
            '<h2>Où ils disent avoir été</h2><div class="tlwrap"><table class="tl">',
        ", your pencil": ", votre crayon",
        '<span><b>?</b>unaccounted for</span></div>': '<span><b>?</b>on ne sait où</span></div>',
        " (the deceased)": " (la victime)",
        '<div class="empty" style="margin-top:12px">Only what somebody has ':
            '<div class="empty" style="margin-top:12px">Seulement ce que quelqu\'un vous a ',
        "told you. Red means two people put them in different rooms at that hour. ":
            "dit. Le rouge signifie que deux personnes les placent dans des pièces "
            "différentes à cette heure. ",
        "The bottom row is where your questions have not reached. A ringed tag was ":
            "La dernière ligne, c'est là où vos questions ne sont pas allées. Une étiquette "
            "cerclée a été ",
        "<h3>Charge ": "<h3>Accuser ",
        "<p>In your own words: what did they do it for? Nothing here is marked. ":
            "<p>Avec vos mots : pourquoi l'a-t-il fait ? Rien ici n'est noté. ",
        "You will see the whole case afterwards and can judge your own answer ":
            "Vous verrez toute l'affaire ensuite et pourrez juger votre réponse ",
        "against it. This ends the game.</p>": "vous-même. Cela termine la partie.</p>",
        '<button id="press" class="accuse">Charge ': '<button id="press" class="accuse">Accuser ',
        '<button id="backout">Not yet</button></div>': '<button id="backout">Pas encore</button></div>',
        '<div class="said">You charged ': '<div class="said">Vous avez accusé ',
        "You named him.": "Vous avez vu juste.",
        "Wrong.": "Erreur.",
        '<div class="who">The killer was <b>': '<div class="who">Le coupable était <b>',
        " asked</div></div>": "</div></div>",
        '<div class="act"><h2>The reason</h2>': '<div class="act"><h2>Le mobile</h2>',
        '<div class="item soft"><span class="tag">what you wrote</span>':
            '<div class="item soft"><span class="tag">ce que vous avez écrit</span>',
        '"><span class="tag">what it was</span>': '"><span class="tag">ce que c\'était</span>',
        '<p class="empty">Nobody is marking this. Read the ':
            '<p class="empty">Personne ne note ceci. Lisez les ',
        "two and decide whether you had it.</p>": "deux et décidez si vous l'aviez trouvé.</p>",
        '<div class="act"><h2>What was not true</h2>': '<div class="act"><h2>Ce qui était faux</h2>',
        "</b> said the ": "</b> a dit ",
        ". They were in the ": ". En réalité dans ",
        '<br><span class="empty">Covering: ': '<br><span class="empty">Pour couvrir : ',
        '<div class="act"><h2>Who could have broken it</h2>':
            '<div class="act"><h2>Qui aurait pu le démentir</h2>',
        "you never asked them": "aucune question",
        '<div class="act"><h2>What you got out of them': '<div class="act"><h2>Ce que vous avez obtenu',
        '<div class="act"><h2>Secrets you never found</h2>':
            '<div class="act"><h2>Les secrets que vous n\'avez pas trouvés</h2>',
        "the police": "les gendarmes",
        "from ": "de ",
        " at ": " à ",
        "asked ": "interrogé ",
    },
}

# --------------------------------------------------------------------------
# Whole pieces of the page: plurals built from parts, the static markup, the
# article the page strips from a room's name.
# --------------------------------------------------------------------------

_SHARED = [
    # "the kitchen" becomes "kitchen" in "found the body in the kitchen"; the
    # translated rooms bring their own articles, which the sentence supplies.
    (
        "replace(/^[Tt]he\\s+/,'')",
        "replace(/^(?:[Tt]he|[Ll][ao]|[Ii]l|[Ll]o|[Gg]li|[Ii]|[Ll]e|[Ll]es)\\s+|^[Ll]['’]/,'')",
    ),
]

SNIPPETS: dict[str, list[tuple[str, str]]] = {
    "it": [
        *_SHARED,
        ('<html lang="en">', '<html lang="it">'),
        ("n.questions+(n.questions===1?' question':' questions')",
         "n.questions+(n.questions===1?' domanda':' domande')"),
        ("left+' question'+(left===1?'':'s')+' left'",
         "left+(left===1?' domanda rimasta':' domande rimaste')"),
        ("' contradiction'+\n      (n.conflicts.length>1?'s':'')",
         "(n.conflicts.length>1?' contraddizioni':' contraddizione')"),
        ("(p.refused===1?' time':' times')", "(p.refused===1?' volta':' volte')"),
        ("(r.questions===1?' question':' questions')",
         "(r.questions===1?' domanda fatta':' domande fatte')"),
        ("<title>Interrogation</title>", "<title>Interrogatorio</title>"),
        (">Interrogation<", ">Interrogatorio<"),
        (">0 questions<", ">0 domande<"),
        (">Case file<", ">Fascicolo<"),
        (">Sound on<", ">Audio sì<"),
        (">Notebook<", ">Taccuino<"),
        (">Accuse<", ">Accusa<"),
        (">Pick someone below and ask them something.<",
         ">Scegli qualcuno qui sotto e fagli una domanda.<"),
        (">Ask<", ">Chiedi<"),
        ('title="What you were told when you arrived"', 'title="Cosa ti hanno detto al tuo arrivo"'),
        ('title="How to play"', 'title="Come si gioca"'),
        ('title="Reading size"', 'title="Dimensione del testo"'),
        ('title="Name who did it"', 'title="Indica il colpevole"'),
        ('placeholder="Ask a question"', 'placeholder="Fai una domanda"'),
        ('title="Drag to resize, double-click to reset"',
         'title="Trascina per ridimensionare, doppio clic per ripristinare"'),
        ('placeholder="Search everything anybody said"',
         'placeholder="Cerca in tutto quello che è stato detto"'),
    ],
    "fr": [
        *_SHARED,
        ('<html lang="en">', '<html lang="fr">'),
        ("n.questions+(n.questions===1?' question':' questions')",
         "n.questions+(n.questions===1?' question':' questions')"),
        ("left+' question'+(left===1?'':'s')+' left'",
         "left+(left===1?' question restante':' questions restantes')"),
        ("' contradiction'+\n      (n.conflicts.length>1?'s':'')",
         "(n.conflicts.length>1?' contradictions':' contradiction')"),
        ("(p.refused===1?' time':' times')", "(p.refused===1?' fois':' fois')"),
        ("(r.questions===1?' question':' questions')",
         "(r.questions===1?' question posée':' questions posées')"),
        ("<title>Interrogation</title>", "<title>Interrogatoire</title>"),
        (">Interrogation<", ">Interrogatoire<"),
        (">0 questions<", ">0 question<"),
        (">Case file<", ">Dossier<"),
        (">Sound on<", ">Son activé<"),
        (">Notebook<", ">Carnet<"),
        (">Accuse<", ">Accuser<"),
        (">Pick someone below and ask them something.<",
         ">Choisissez quelqu'un ci-dessous et posez-lui une question.<"),
        (">Ask<", ">Demander<"),
        ('title="What you were told when you arrived"',
         'title="Ce qu\'on vous a dit à votre arrivée"'),
        ('title="How to play"', 'title="Comment jouer"'),
        ('title="Reading size"', 'title="Taille du texte"'),
        ('title="Name who did it"', 'title="Nommer le coupable"'),
        ('placeholder="Ask a question"', 'placeholder="Posez une question"'),
        ('title="Drag to resize, double-click to reset"',
         'title="Glisser pour redimensionner, double-clic pour réinitialiser"'),
        ('placeholder="Search everything anybody said"',
         'placeholder="Chercher dans tout ce qui a été dit"'),
    ],
}


def _quoted(text: str, quote: str) -> str:
    return text.replace("\\", "\\\\").replace(quote, "\\" + quote).replace("\n", "\\n")


def translate_page(page: str, lang: str) -> str:
    """`page` with its words in `lang`; English for "en" or anything unknown."""
    from mystery.jsscan import string_literals

    if lang not in LITERALS:
        return page
    table = LITERALS[lang]
    out, last = [], 0
    for match in re.finditer(r"<script>(.*?)</script>", page, re.S):
        base = match.start(1)
        for start, end, quote, content in string_literals(match.group(1)):
            if quote == "`" or content not in table:
                continue
            out.append(page[last:base + start])
            out.append(quote + _quoted(table[content], quote) + quote)
            last = base + end
    out.append(page[last:])
    page = "".join(out)
    # After the literals, so that a snippet like ">Accuse<" cannot change a
    # literal before the table has had the chance to match it whole.
    for english, translated in SNIPPETS.get(lang, []):
        page = page.replace(english, translated)
    return page


@cache
def page_in(lang: str) -> str:
    """The page for a room in `lang`, made once per process."""
    from mystery.web import PAGE

    return translate_page(PAGE, lang)
