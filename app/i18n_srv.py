# Messages of the server, the generator checks and the build log in the app languages.
# Keys are the English texts (with %-placeholders); German for generator messages comes from translations_de.py.
MSG = {
    # ---- server
    "cobra-tools was not found. Please install the program again.": {
        "de": "cobra-tools wurde nicht gefunden. Bitte das Programm neu installieren.",
        "fr": "cobra-tools est introuvable. Veuillez réinstaller le programme.",
        "es": "No se encontró cobra-tools. Vuelve a instalar el programa.",
        "zh": "未找到 cobra-tools。请重新安装程序。",
        "ja": "cobra-tools が見つかりません。プログラムを再インストールしてください。"},
    "Invalid ID '%s': 3-31 lowercase letters, digits and _, starting with a letter.": {
        "de": "Ungültige ID '%s': 3-31 Kleinbuchstaben, Ziffern und _, am Anfang ein Buchstabe.",
        "fr": "ID '%s' invalide : 3 à 31 lettres minuscules, chiffres et _, en commençant par une lettre.",
        "es": "ID '%s' no válido: 3-31 letras minúsculas, dígitos y _, empezando por una letra.",
        "zh": "无效的 ID '%s'：3-31 个小写字母、数字和 _，须以字母开头。",
        "ja": "無効な ID '%s'：英小文字・数字・_ の 3〜31 文字で、先頭は英字にしてください。"},
    "The ID '%s' is already used by another tribune ('%s'). Enter another ID under 'More' or delete the other tribune.": {
        "de": "Die ID '%s' benutzt schon eine andere Tribüne ('%s'). Bitte unter 'Mehr' eine andere ID eintragen oder die andere Tribüne löschen.",
        "fr": "L'ID '%s' est déjà utilisé par une autre tribune ('%s'). Saisissez un autre ID sous « Plus » ou supprimez l'autre tribune.",
        "es": "El ID '%s' ya lo usa otra grada ('%s'). Introduce otro ID en «Más» o borra la otra grada.",
        "zh": "ID '%s' 已被另一个看台（'%s'）使用。请在“更多”中输入其他 ID，或删除另一个看台。",
        "ja": "ID '%s' は別のスタンド（'%s'）で使われています。「その他」で別の ID を入力するか、もう一方を削除してください。"},
    "Generating tribune ...": {"de": "Erzeuge Tribüne ...", "fr": "Génération de la tribune ...", "es": "Generando la grada ...",
                               "zh": "正在生成看台 ...", "ja": "スタンドを生成中 ..."},
    "Not saved: %s": {"de": "Nicht gespeichert: %s", "fr": "Non enregistré : %s", "es": "No guardado: %s", "zh": "未保存：%s",
                      "ja": "保存されませんでした：%s"},
    "Building model ...": {"de": "Baue Modell ...", "fr": "Construction du modèle ...", "es": "Construyendo el modelo ...",
                           "zh": "正在构建模型 ...", "ja": "モデルを作成中 ..."},
    "Saving to the library (model, materials, patterns, icon) ...": {
        "de": "Speichere in der Bibliothek (Modell, Material, Muster, Icon) ...",
        "fr": "Enregistrement dans la bibliothèque (modèle, matériaux, motifs, icône) ...",
        "es": "Guardando en la biblioteca (modelo, materiales, patrones, icono) ...",
        "zh": "正在保存到库（模型、材质、纹理、图标）...", "ja": "ライブラリに保存中（モデル・マテリアル・パターン・アイコン）..."},
    "Saved: %s (%s, %d seats)": {"de": "Gespeichert: %s (%s, %d Sitze)", "fr": "Enregistré : %s (%s, %d places)",
                                 "es": "Guardado: %s (%s, %d asientos)", "zh": "已保存：%s（%s，%d 个座位）",
                                 "ja": "保存しました：%s（%s、%d 席）"},
    "Planet Coaster 2 was not found (with the Silver Screen DLC). Please choose the ovldata folder in the settings: ...\\steamapps\\common\\Planet Coaster 2\\Win64\\ovldata": {
        "de": "Planet Coaster 2 wurde nicht gefunden (mit Silver-Screen-DLC). Bitte unter Einstellungen den ovldata-Ordner angeben: ...\\steamapps\\common\\Planet Coaster 2\\Win64\\ovldata",
        "fr": "Planet Coaster 2 est introuvable (avec le DLC Silver Screen). Choisissez le dossier ovldata dans les paramètres : ...\\steamapps\\common\\Planet Coaster 2\\Win64\\ovldata",
        "es": "No se encontró Planet Coaster 2 (con el DLC Silver Screen). Elige la carpeta ovldata en los ajustes: ...\\steamapps\\common\\Planet Coaster 2\\Win64\\ovldata",
        "zh": "未找到 Planet Coaster 2（需要 Silver Screen DLC）。请在设置中选择 ovldata 文件夹：...\\steamapps\\common\\Planet Coaster 2\\Win64\\ovldata",
        "ja": "Planet Coaster 2（Silver Screen DLC 付き）が見つかりません。設定で ovldata フォルダーを選んでください：...\\steamapps\\common\\Planet Coaster 2\\Win64\\ovldata"},
    "A Python package is missing (%s). Please start the app again.": {
        "de": "Ein Python-Paket fehlt (%s). Bitte die App neu starten.",
        "fr": "Un paquet Python manque (%s). Relancez l'application.", "es": "Falta un paquete de Python (%s). Vuelve a iniciar la aplicación.",
        "zh": "缺少 Python 包（%s）。请重新启动应用。", "ja": "Python パッケージが不足しています（%s）。アプリを再起動してください。"},
    "Planet Coaster 2 was not found. Please choose the ovldata folder in the settings first.": {
        "de": "Planet Coaster 2 wurde nicht gefunden. Bitte zuerst in den Einstellungen den ovldata-Ordner wählen.",
        "fr": "Planet Coaster 2 est introuvable. Choisissez d'abord le dossier ovldata dans les paramètres.",
        "es": "No se encontró Planet Coaster 2. Elige primero la carpeta ovldata en los ajustes.",
        "zh": "未找到 Planet Coaster 2。请先在设置中选择 ovldata 文件夹。",
        "ja": "Planet Coaster 2 が見つかりません。先に設定で ovldata フォルダーを選んでください。"},
    "Building all tribunes of the library as mods ...": {
        "de": "Baue alle Tribünen der Bibliothek als Mods ...", "fr": "Construction de toutes les tribunes de la bibliothèque en mods ...",
        "es": "Construyendo todas las gradas de la biblioteca como mods ...", "zh": "正在将库中所有看台构建为模组 ...",
        "ja": "ライブラリのすべてのスタンドを MOD として作成中 ..."},
    "This tribune was made in the Blender add-on and cannot be edited here.": {
        "de": "Diese Tribüne wurde im Blender-Add-on gebaut und kann hier nicht bearbeitet werden.",
        "fr": "Cette tribune a été créée avec l'extension Blender et ne peut pas être modifiée ici.",
        "es": "Esta grada se creó con el complemento de Blender y no se puede editar aquí.",
        "zh": "此看台由 Blender 插件创建，无法在此编辑。", "ja": "このスタンドは Blender アドオンで作られたため、ここでは編集できません。"},
    # ---- build log
    "library: %s (%d tribunes)": {"de": "Bibliothek: %s (%d Tribünen)", "fr": "bibliothèque : %s (%d tribunes)",
                                  "es": "biblioteca: %s (%d gradas)", "zh": "库：%s（%d 个看台）", "ja": "ライブラリ：%s（%d 基）"},
    "reading the cinema ride (one time) ...": {"de": "lese die Kino-Attraktion (einmalig) ...", "fr": "lecture de l'attraction cinéma (une seule fois) ...",
                                               "es": "leyendo la atracción del cine (una vez) ...", "zh": "正在读取影院游乐设施（仅一次）...",
                                               "ja": "シネマのアトラクションを読み込み中（初回のみ）..."},
    "cinema templates ready": {"de": "Kino-Vorlagen fertig", "fr": "modèles du cinéma prêts", "es": "plantillas del cine listas",
                               "zh": "影院模板已就绪", "ja": "シネマのテンプレート準備完了"},
    "packed %s (%d files)": {"de": "gepackt: %s (%d Dateien)", "fr": "empaqueté : %s (%d fichiers)", "es": "empaquetado: %s (%d archivos)",
                             "zh": "已打包：%s（%d 个文件）", "ja": "パック済み：%s（%d ファイル）"},
    "built %s: %s (%d seats)": {"de": "gebaut: %s: %s (%d Sitze)", "fr": "construit %s : %s (%d places)", "es": "construido %s: %s (%d asientos)",
                                "zh": "已构建 %s：%s（%d 个座位）", "ja": "作成済み %s：%s（%d 席）"},
    "in the mod: %s -> %s (%d seats)": {"de": "installiert: %s -> %s (%d Sitze)", "fr": "installé : %s -> %s (%d places)",
                                        "es": "instalado: %s -> %s (%d asientos)", "zh": "已安装：%s -> %s（%d 个座位）",
                                        "ja": "インストール済み：%s -> %s（%d 席）"},
    "removed old mod folder %s": {"de": "alter Mod-Ordner entfernt: %s", "fr": "ancien dossier de mod supprimé : %s",
                                  "es": "carpeta de mod antigua eliminada: %s", "zh": "已删除旧模组文件夹：%s", "ja": "古い MOD フォルダーを削除：%s"},
    "saved %s to the library (%d seats)": {"de": "%s in der Bibliothek gespeichert (%d Sitze)", "fr": "%s enregistré dans la bibliothèque (%d places)",
                                           "es": "%s guardado en la biblioteca (%d asientos)", "zh": "%s 已保存到库（%d 个座位）",
                                           "ja": "%s をライブラリに保存（%d 席）"},
    # ---- generator and checks (German: translations_de.py)
    "The front line needs at least one segment with a length.": {
        "fr": "La ligne avant a besoin d'au moins un segment avec une longueur.", "es": "La línea frontal necesita al menos un tramo con longitud.",
        "zh": "前沿线至少需要一段有长度的线段。", "ja": "前縁ラインには長さのある区間が少なくとも 1 つ必要です。"},
    "A corner is too sharp (more than about 135 degrees).": {
        "fr": "Un angle est trop aigu (plus d'environ 135 degrés).", "es": "Una esquina es demasiado cerrada (más de unos 135 grados).",
        "zh": "某个转角过于尖锐（超过约 135 度）。", "ja": "角が鋭すぎます（約 135 度を超えています）。"},
    "A corner bends towards the rows and the rows are too deep for it. Use a smaller angle, a longer segment or fewer rows.": {
        "fr": "Un angle se replie vers les rangées et celles-ci sont trop profondes. Utilisez un angle plus petit, un segment plus long ou moins de rangées.",
        "es": "Una esquina se dobla hacia las filas y estas son demasiado profundas. Usa un ángulo menor, un tramo más largo o menos filas.",
        "zh": "某个转角向座排方向弯折，而座排太深。请减小角度、加长线段或减少排数。",
        "ja": "角が列側に折れていて、列が深すぎます。角度を小さくするか、区間を長くするか、列を減らしてください。"},
    "At least one row is needed.": {"fr": "Il faut au moins une rangée.", "es": "Se necesita al menos una fila.", "zh": "至少需要一排。",
                                    "ja": "少なくとも 1 列必要です。"},
    "The rows are too shallow for the seats: the walking lane in front of the seats is %.2f m, it needs at least 0.40 m. Increase the row depth to %.2f m or more.": {
        "fr": "Les rangées sont trop étroites pour les sièges : le passage devant les sièges fait %.2f m, il faut au moins 0,40 m. Augmentez la profondeur de rangée à %.2f m ou plus.",
        "es": "Las filas son demasiado estrechas para los asientos: el pasillo delante mide %.2f m y necesita al menos 0,40 m. Aumenta la profundidad de fila a %.2f m o más.",
        "zh": "座排太浅：座椅前的通道为 %.2f 米，至少需要 0.40 米。请将排深增加到 %.2f 米或以上。",
        "ja": "列が浅すぎます：座席前の通路は %.2f m で、最低 0.40 m 必要です。列の奥行きを %.2f m 以上にしてください。"},
    "The seats hang over the next step but are too low for it (seat bottom %.2f m, rise %.2f m). Use a seat back gap of 0 or more.": {
        "fr": "Les sièges dépassent sur la marche suivante mais sont trop bas (bas du siège %.2f m, hauteur %.2f m). Utilisez un écart au bord de 0 ou plus.",
        "es": "Los asientos sobresalen sobre el siguiente escalón pero están demasiado bajos (base %.2f m, altura %.2f m). Usa una distancia al borde de 0 o más.",
        "zh": "座椅伸出到下一级台阶上方但过低（座椅底部 %.2f 米，台阶高 %.2f 米）。请将到台阶边缘的距离设为 0 或以上。",
        "ja": "座席が次の段の上に張り出していますが低すぎます（座面下 %.2f m、段差 %.2f m）。段の縁までの距離を 0 以上にしてください。"},
    "Walking lane only %.2f m wide: guests walk in single file.": {
        "fr": "Passage de seulement %.2f m : les visiteurs marchent en file indienne.", "es": "Pasillo de solo %.2f m: los visitantes caminan en fila.",
        "zh": "通道仅 %.2f 米宽：游客将单列通行。", "ja": "通路の幅が %.2f m しかありません：来場者は一列で歩きます。"},
    "The first row is too shallow: increase its depth to %.2f m or more.": {
        "fr": "La première rangée est trop étroite : augmentez sa profondeur à %.2f m ou plus.",
        "es": "La primera fila es demasiado estrecha: aumenta su profundidad a %.2f m o más.",
        "zh": "第一排太浅：请将其深度增加到 %.2f 米或以上。", "ja": "最前列が浅すぎます：奥行きを %.2f m 以上にしてください。"},
    "The aisle stairs are steep (%.0f %%). Guests may refuse them; use a smaller rise or deeper rows.": {
        "fr": "Les escaliers sont raides (%.0f %%). Les visiteurs risquent de les éviter ; réduisez la hauteur ou approfondissez les rangées.",
        "es": "Las escaleras son empinadas (%.0f %%). Los visitantes pueden evitarlas; usa menos altura o filas más profundas.",
        "zh": "楼梯很陡（%.0f %%）。游客可能拒绝使用；请减小高度或加深座排。",
        "ja": "階段が急です（%.0f %%）。来場者が避ける可能性があります。段差を小さくするか列を深くしてください。"},
    "No stairs: switch on at least one aisle so guests can reach the rows.": {
        "fr": "Aucun escalier : activez-en au moins un pour que les visiteurs atteignent les rangées.",
        "es": "Sin escaleras: activa al menos una para que los visitantes lleguen a las filas.",
        "zh": "没有楼梯：请至少开启一个楼梯，游客才能到达座排。", "ja": "階段がありません：来場者が列に行けるよう、少なくとも 1 つ有効にしてください。"},
    "Without the front walkway the middle stairs start at the first row.": {
        "fr": "Sans passage avant, les escaliers du milieu commencent à la première rangée.",
        "es": "Sin el pasillo delantero, las escaleras centrales empiezan en la primera fila.",
        "zh": "没有前方通道时，中间楼梯从第一排开始。", "ja": "前方通路がないと、中央の階段は最前列から始まります。"},
    "The show area was shortened to %.1f m %s.": {
        "fr": "La zone de spectacle a été raccourcie à %.1f m %s.", "es": "La zona del espectáculo se acortó a %.1f m %s.",
        "zh": "表演区已缩短为 %.1f 米 %s。", "ja": "ショーエリアを %.1f m に短縮しました %s。"},
    "No walkway in front of the tribune; a 0.5 m strip was added.": {
        "fr": "Pas de passage devant la tribune ; une bande de 0,5 m a été ajoutée.", "es": "No hay pasillo delante de la grada; se añadió una franja de 0,5 m.",
        "zh": "看台前没有通道；已添加 0.5 米的通道。", "ja": "スタンドの前に通路がないため、0.5 m の通路を追加しました。"},
    "The navmesh is too big. Use fewer arc pieces or a smaller tribune.": {
        "fr": "Le maillage de navigation est trop grand. Utilisez moins de segments d'arc ou une tribune plus petite.",
        "es": "La malla de navegación es demasiado grande. Usa menos tramos de arco o una grada más pequeña.",
        "zh": "导航网格过大。请减少弧段数量或缩小看台。", "ja": "ナビメッシュが大きすぎます。円弧の分割を減らすか、スタンドを小さくしてください。"},
    "No seats fit. Make the tribune longer or the aisles narrower.": {
        "fr": "Aucun siège ne rentre. Allongez la tribune ou réduisez la largeur des escaliers.",
        "es": "No caben asientos. Alarga la grada o estrecha las escaleras.", "zh": "放不下座椅。请加长看台或减小楼梯宽度。",
        "ja": "座席が入りません。スタンドを長くするか、階段を狭くしてください。"},
    "%d seats: very large tribunes can be slow in the game.": {
        "fr": "%d places : les très grandes tribunes peuvent ralentir le jeu.", "es": "%d asientos: las gradas muy grandes pueden ralentizar el juego.",
        "zh": "%d 个座位：超大看台可能导致游戏变慢。", "ja": "%d 席：非常に大きなスタンドはゲームが重くなることがあります。"},
    "Choose at least one entrance side.": {"fr": "Choisissez au moins un côté d'entrée.", "es": "Elige al menos un lado de entrada.",
                                           "zh": "请至少选择一个入口方向。", "ja": "入口を少なくとも 1 方向選んでください。"},
    "No side or back walkway: the ride booth was put on the show area.": {
        "fr": "Pas de passage latéral ni arrière : la cabine a été placée sur la zone de spectacle.",
        "es": "Sin pasillo lateral ni trasero: la cabina se colocó en la zona del espectáculo.",
        "zh": "没有侧面或后方通道：操作亭已放到表演区。", "ja": "側面・後方の通路がないため、操作ブースをショーエリアに置きました。"},
    "The navmesh is empty.": {"fr": "Le maillage de navigation est vide.", "es": "La malla de navegación está vacía.", "zh": "导航网格为空。",
                              "ja": "ナビメッシュが空です。"},
    "The navmesh has %d points, the game allows 65000.": {
        "fr": "Le maillage de navigation a %d points, le jeu en autorise 65000.", "es": "La malla de navegación tiene %d puntos; el juego permite 65000.",
        "zh": "导航网格有 %d 个点，游戏最多允许 65000 个。", "ja": "ナビメッシュの点が %d 個あります（上限 65000）。"},
    "No walkable ground touches an entrance edge of the outline.": {
        "fr": "Aucune zone praticable ne touche une entrée du contour.", "es": "Ninguna zona transitable toca una entrada del contorno.",
        "zh": "没有可行走区域接触到轮廓的入口边。", "ja": "歩ける面が外形の入口に接していません。"},
    "%d walkable island(s) cannot be reached from an entrance (%d triangles).": {
        "fr": "%d îlot(s) praticable(s) inaccessible(s) depuis une entrée (%d triangles).",
        "es": "%d isla(s) transitable(s) no alcanzable(s) desde una entrada (%d triángulos).",
        "zh": "%d 个可行走区域无法从入口到达（%d 个三角形）。", "ja": "入口から到達できない歩行エリアが %d 個あります（三角形 %d 個）。"},
    "%d seat(s) cannot be reached.": {"fr": "%d place(s) inaccessible(s).", "es": "%d asiento(s) no alcanzable(s).",
                                      "zh": "%d 个座位无法到达。", "ja": "%d 席に到達できません。"},
}
