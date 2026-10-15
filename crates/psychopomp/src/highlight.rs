//! Small highlighters that compile one source line into styled spans for the
//! editor recipe: TypeScript/JavaScript, C#, and XML (MSBuild files). Roles follow
//! the Presentation Theme syntax mapping: keywords, function calls as the accent,
//! capitalized names as types, strings, muted comments, and numbers; XML tags read
//! as keywords and attribute names as types. Each is a line-local approximation
//! for explainers, not a parser: template literals, verbatim strings, and comments
//! that span lines are not tracked.
use crate::code::{StyledSpan, SyntaxStyle};

const TYPESCRIPT: &[&str] = &[
    "as",
    "async",
    "await",
    "break",
    "case",
    "catch",
    "class",
    "const",
    "continue",
    "default",
    "delete",
    "do",
    "else",
    "export",
    "extends",
    "false",
    "finally",
    "for",
    "from",
    "function",
    "if",
    "import",
    "in",
    "instanceof",
    "interface",
    "let",
    "new",
    "null",
    "of",
    "return",
    "switch",
    "this",
    "throw",
    "true",
    "try",
    "type",
    "typeof",
    "undefined",
    "var",
    "void",
    "while",
    "yield",
];

/// C# keywords, including the lowercase built-in type names (`bool`, `byte`)
/// that the capitalized-name rule would otherwise leave plain.
const CSHARP: &[&str] = &[
    "abstract",
    "as",
    "async",
    "await",
    "base",
    "bool",
    "break",
    "byte",
    "case",
    "catch",
    "char",
    "checked",
    "class",
    "const",
    "continue",
    "decimal",
    "default",
    "delegate",
    "do",
    "double",
    "else",
    "enum",
    "event",
    "explicit",
    "extern",
    "false",
    "finally",
    "fixed",
    "float",
    "for",
    "foreach",
    "goto",
    "if",
    "implicit",
    "in",
    "int",
    "interface",
    "internal",
    "is",
    "lock",
    "long",
    "nameof",
    "namespace",
    "new",
    "not",
    "null",
    "object",
    "operator",
    "out",
    "override",
    "params",
    "partial",
    "private",
    "protected",
    "public",
    "readonly",
    "record",
    "ref",
    "return",
    "sbyte",
    "sealed",
    "short",
    "sizeof",
    "stackalloc",
    "static",
    "string",
    "struct",
    "switch",
    "this",
    "throw",
    "true",
    "try",
    "typeof",
    "uint",
    "ulong",
    "unchecked",
    "unsafe",
    "ushort",
    "using",
    "var",
    "virtual",
    "void",
    "volatile",
    "while",
    "yield",
];

/// Muted gray: neutral, so every theme maps it to its muted text color.
pub const COMMENT: SyntaxStyle = SyntaxStyle::Rgb(128, 128, 128);
/// Numbers keep one warm color in every theme.
pub const NUMBER: SyntaxStyle = SyntaxStyle::Rgb(245, 167, 66);

/// The highlighter for `file_name`'s extension: C# for `.cs`, XML for `.xml` and
/// MSBuild files, and TypeScript for everything else.
pub fn for_file(file_name: &str) -> fn(&str) -> Vec<StyledSpan> {
    match file_name.rsplit('.').next().unwrap_or_default() {
        "cs" => csharp,
        "xml" | "props" | "targets" | "csproj" => xml,
        _ => typescript,
    }
}

/// How a C-like language spells its words and strings.
struct Syntax {
    keywords: &'static [&'static str],
    quotes: &'static [char],
    /// Characters besides letters, digits, and `_` that identifiers may contain.
    word: &'static [char],
}

pub fn typescript(line: &str) -> Vec<StyledSpan> {
    c_like(
        line,
        &Syntax {
            keywords: TYPESCRIPT,
            quotes: &['"', '\'', '`'],
            word: &['$'],
        },
    )
}

pub fn csharp(line: &str) -> Vec<StyledSpan> {
    c_like(
        line,
        &Syntax {
            keywords: CSHARP,
            quotes: &['"', '\''],
            word: &[],
        },
    )
}

/// Appends `text` in `style`, merging it into the last span when the styles match.
fn push(spans: &mut Vec<StyledSpan>, text: &str, style: SyntaxStyle) {
    if text.is_empty() {
        return;
    }
    match spans.last_mut() {
        Some(last) if same(last.style, style) => last.text.push_str(text),
        _ => spans.push(StyledSpan::new(text, style)),
    }
}

fn c_like(line: &str, syntax: &Syntax) -> Vec<StyledSpan> {
    let chars = line.char_indices().collect::<Vec<_>>();
    let mut spans: Vec<StyledSpan> = Vec::new();
    let word = |c: char| c.is_alphanumeric() || c == '_' || syntax.word.contains(&c);
    let slice = |from: usize, to: usize| {
        let start = chars.get(from).map_or(line.len(), |(i, _)| *i);
        let end = chars.get(to).map_or(line.len(), |(i, _)| *i);
        &line[start..end]
    };
    let mut index = 0;
    while index < chars.len() {
        let c = chars[index].1;
        if c == '/' && chars.get(index + 1).is_some_and(|(_, n)| *n == '/') {
            push(&mut spans, slice(index, chars.len()), COMMENT);
            break;
        }
        if syntax.quotes.contains(&c) {
            let mut end = index + 1;
            while end < chars.len() && chars[end].1 != c {
                end += if chars[end].1 == '\\' { 2 } else { 1 };
            }
            let end = (end + 1).min(chars.len());
            push(&mut spans, slice(index, end), SyntaxStyle::String);
            index = end;
            continue;
        }
        if c.is_ascii_digit() {
            let mut end = index + 1;
            while end < chars.len()
                && (chars[end].1.is_ascii_alphanumeric() || matches!(chars[end].1, '_' | '.'))
            {
                end += 1;
            }
            push(&mut spans, slice(index, end), NUMBER);
            index = end;
            continue;
        }
        if word(c) && !c.is_numeric() {
            let mut end = index + 1;
            while end < chars.len() && word(chars[end].1) {
                end += 1;
            }
            let word = slice(index, end);
            let called = chars[end..]
                .iter()
                .map(|(_, c)| *c)
                .find(|c| !c.is_whitespace())
                == Some('(');
            let member = index > 0 && chars[index - 1].1 == '.';
            let style = if syntax.keywords.contains(&word) && !member {
                SyntaxStyle::Keyword
            } else if called {
                SyntaxStyle::Accent
            } else if word.chars().next().is_some_and(char::is_uppercase) {
                SyntaxStyle::Type
            } else {
                SyntaxStyle::Plain
            };
            push(&mut spans, word, style);
            index = end;
            continue;
        }
        push(&mut spans, slice(index, index + 1), SyntaxStyle::Plain);
        index += 1;
    }
    spans
}

/// XML: tag names as keywords, attribute names as types, quoted values as
/// strings, comments muted, and markup punctuation and text between tags plain.
pub fn xml(line: &str) -> Vec<StyledSpan> {
    let mut spans: Vec<StyledSpan> = Vec::new();
    let name = |c: char| c.is_alphanumeric() || matches!(c, '_' | '-' | '.' | ':');
    let mut rest = line;
    let mut in_tag = false;
    while let Some(c) = rest.chars().next() {
        let (text, style, tag) = if !in_tag && rest.starts_with("<!--") {
            let end = rest.find("-->").map_or(rest.len(), |at| at + 3);
            (&rest[..end], COMMENT, false)
        } else if !in_tag && c == '<' {
            let open = if rest.starts_with("</") { 2 } else { 1 };
            (&rest[..open], SyntaxStyle::Plain, true)
        } else if !in_tag {
            (
                &rest[..rest.find('<').unwrap_or(rest.len())],
                SyntaxStyle::Plain,
                false,
            )
        } else if c == '>' || rest.starts_with("/>") {
            let close = if c == '>' { 1 } else { 2 };
            (&rest[..close], SyntaxStyle::Plain, false)
        } else if matches!(c, '"' | '\'') {
            let end = rest[1..].find(c).map_or(rest.len(), |at| at + 2);
            (&rest[..end], SyntaxStyle::String, true)
        } else if name(c) {
            let end = rest.find(|c: char| !name(c)).unwrap_or(rest.len());
            // The first name after `<` or `</` is the tag; later names are attributes.
            let style = match spans.last() {
                Some(last) if last.text.ends_with('<') || last.text.ends_with("</") => {
                    SyntaxStyle::Keyword
                }
                _ => SyntaxStyle::Type,
            };
            (&rest[..end], style, true)
        } else {
            (&rest[..c.len_utf8()], SyntaxStyle::Plain, true)
        };
        push(&mut spans, text, style);
        in_tag = tag;
        rest = &rest[text.len()..];
    }
    spans
}

fn same(a: SyntaxStyle, b: SyntaxStyle) -> bool {
    use SyntaxStyle::*;
    match (a, b) {
        (Plain, Plain)
        | (Keyword, Keyword)
        | (Type, Type)
        | (String, String)
        | (Accent, Accent) => true,
        (Rgb(r1, g1, b1), Rgb(r2, g2, b2)) => (r1, g1, b1) == (r2, g2, b2),
        _ => false,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn styles(line: &str) -> Vec<(String, &'static str)> {
        roles(typescript(line))
    }

    fn roles(spans: Vec<StyledSpan>) -> Vec<(String, &'static str)> {
        spans
            .into_iter()
            .map(|span| {
                let name = match span.style {
                    SyntaxStyle::Plain => "plain",
                    SyntaxStyle::Keyword => "keyword",
                    SyntaxStyle::Type => "type",
                    SyntaxStyle::String => "string",
                    SyntaxStyle::Accent => "accent",
                    SyntaxStyle::Rgb(128, 128, 128) => "comment",
                    SyntaxStyle::Rgb(..) => "number",
                };
                (span.text, name)
            })
            .collect()
    }

    #[test]
    fn roles_follow_the_theme_syntax_mapping() {
        assert_eq!(
            styles(r#"const failure = new Error("port in use") // why"#),
            vec![
                ("const".into(), "keyword"),
                (" failure = ".into(), "plain"),
                ("new".into(), "keyword"),
                (" ".into(), "plain"),
                ("Error".into(), "accent"),
                ("(".into(), "plain"),
                ("\"port in use\"".into(), "string"),
                (") ".into(), "plain"),
                ("// why".into(), "comment"),
            ]
        );
        assert_eq!(
            styles("yield* Effect.sleep(100)"),
            vec![
                ("yield".into(), "keyword"),
                ("* ".into(), "plain"),
                ("Effect".into(), "type"),
                (".".into(), "plain"),
                ("sleep".into(), "accent"),
                ("(".into(), "plain"),
                ("100".into(), "number"),
                (")".into(), "plain"),
            ]
        );
    }

    #[test]
    fn member_names_are_not_keywords_and_text_is_preserved() {
        let line = r#"  if (error.type === "a\"b") return x.default"#;
        let spans = typescript(line);
        assert_eq!(
            spans.iter().map(|s| s.text.as_str()).collect::<String>(),
            line
        );
        let last = spans.last().unwrap();
        assert!(last.text.ends_with("x.default") && matches!(last.style, SyntaxStyle::Plain));
        assert!(styles(line).contains(&("\"a\\\"b\"".into(), "string")));
    }

    #[test]
    fn csharp_keywords_include_its_lowercase_type_names() {
        assert_eq!(
            roles(csharp("public static bool Verify(ReadOnlySpan<byte> key)")),
            vec![
                ("public".into(), "keyword"),
                (" ".into(), "plain"),
                ("static".into(), "keyword"),
                (" ".into(), "plain"),
                ("bool".into(), "keyword"),
                (" ".into(), "plain"),
                ("Verify".into(), "accent"),
                ("(".into(), "plain"),
                ("ReadOnlySpan".into(), "type"),
                ("<".into(), "plain"),
                ("byte".into(), "keyword"),
                ("> key)".into(), "plain"),
            ]
        );
        assert_eq!(
            roles(csharp("var $x = `a`")),
            vec![("var".into(), "keyword"), (" $x = `a`".into(), "plain"),],
            "C# has no backtick strings or `$` in names"
        );
    }

    #[test]
    fn xml_tags_attributes_values_and_comments_take_their_roles() {
        assert_eq!(
            roles(xml("  <RuntimeLibrary>MultiThreaded</RuntimeLibrary>")),
            vec![
                ("  <".into(), "plain"),
                ("RuntimeLibrary".into(), "keyword"),
                (">MultiThreaded</".into(), "plain"),
                ("RuntimeLibrary".into(), "keyword"),
                (">".into(), "plain"),
            ]
        );
        assert_eq!(
            roles(xml(r#"<Group Condition="'$(A)' == 'B'">"#)),
            vec![
                ("<".into(), "plain"),
                ("Group".into(), "keyword"),
                (" ".into(), "plain"),
                ("Condition".into(), "type"),
                ("=".into(), "plain"),
                (r#""'$(A)' == 'B'""#.into(), "string"),
                (">".into(), "plain"),
            ]
        );
        assert_eq!(
            roles(xml("<!-- static CRT --> <Link/>")),
            vec![
                ("<!-- static CRT -->".into(), "comment"),
                (" <".into(), "plain"),
                ("Link".into(), "keyword"),
                ("/>".into(), "plain"),
            ]
        );
        let line = r#"<a b="c" d='e'>f <!-- g"#;
        assert_eq!(
            xml(line)
                .iter()
                .map(|s| s.text.as_str())
                .collect::<String>(),
            line,
            "text is preserved, even in an unclosed comment"
        );
    }

    #[test]
    fn the_file_extension_picks_the_highlighter() {
        let first = |file: &str, line: &str| roles(for_file(file)(line)).remove(0);
        assert_eq!(first("Verify.cs", "public x"), ("public".into(), "keyword"));
        assert_eq!(first("verify.ts", "public x"), ("public x".into(), "plain"));
        assert_eq!(
            first("app.tsx + bootstrap.ts", "const x"),
            ("const".into(), "keyword")
        );
        assert_eq!(first("static-crt.props", "<Link>"), ("<".into(), "plain"));
        assert_eq!(roles(for_file("a.props")("<Link>"))[1].1, "keyword");
    }
}
