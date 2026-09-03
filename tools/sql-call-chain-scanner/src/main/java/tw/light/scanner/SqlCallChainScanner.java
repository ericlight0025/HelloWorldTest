package tw.light.scanner;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.Deque;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Collectors;
import java.util.stream.Stream;

/**
 * JSP／JS／Controller／Service／DAO／SQL 呼叫鏈掃描器。
 *
 * 使用方式：
 * mvn clean package
 * java -jar target/sql-call-chain-scanner-1.0.0.jar <專案路徑> <入口關鍵字> [輸出檔]
 *
 * 範例：
 * java -jar target/sql-call-chain-scanner-1.0.0.jar D:/project order.jsp report.md
 * java -jar target/sql-call-chain-scanner-1.0.0.jar D:/project /order/query report.md
 *
 * 本工具採用靜態文字與簡易方法範圍分析，適合先快速縮小範圍；
 * Java 反射、字串動態組合、框架代理及 JSP runtime include 仍需人工複核。
 */
public class SqlCallChainScanner {

    private static final Set<String> EXTENSIONS = Set.of(
            ".java", ".js", ".jsp", ".jspx", ".sql", ".xml", ".html"
    );
    private static final Pattern JAVA_METHOD = Pattern.compile(
            "(?m)(?:public|protected|private|static|final|synchronized|native|abstract|\n|\\s)+"
                    + "[\\w<>?,.\\[\\]]+\\s+(\\w+)\\s*\\([^;{}]*\\)\\s*\\{");
    private static final Pattern JAVA_CLASS = Pattern.compile("\\bclass\\s+(\\w+)");
    private static final Pattern ANNOTATION_PATH = Pattern.compile(
            "@(GetMapping|PostMapping|PutMapping|DeleteMapping|RequestMapping)\\s*\\([^)]*?['\"]([^'\"]+)['\"]");
    private static final Pattern JS_FUNCTION = Pattern.compile(
            "(?m)(?:function\\s+(\\w+)\\s*\\([^)]*\\)|(?:const|let|var)\\s+(\\w+)\\s*=\\s*function\\s*\\([^)]*\\)|(?:const|let|var)\\s+(\\w+)\\s*=\\s*\\([^)]*\\)\\s*=>)\\s*\\{");
    private static final Pattern SQL = Pattern.compile("(?i)\\b(select|insert\\s+into|update|delete\\s+from)\\b");

    private final Map<String, Node> nodes = new LinkedHashMap<>();
    private final Map<String, List<Node>> methodIndex = new HashMap<>();
    private final List<String> warnings = new ArrayList<>();

    public static void main(String[] args) throws IOException {
        if (args.length < 2 || args.length > 3) {
            System.out.println("使用方式：java -jar scanner.jar <專案路徑> <入口關鍵字> [輸出檔]");
            System.out.println("範例：java -jar scanner.jar D:/project order.jsp report.md");
            return;
        }
        Path root = Paths.get(args[0]).toAbsolutePath().normalize();
        String entry = args[1];
        Path output = args.length == 3 ? Paths.get(args[2]) : root.resolve("sql-call-chain-report.md");
        SqlCallChainScanner scanner = new SqlCallChainScanner();
        scanner.scan(root);
        String report = scanner.buildReport(root, entry);
        Files.writeString(output, report, StandardCharsets.UTF_8);
        System.out.println(report);
        System.out.println("\n報告已輸出：" + output.toAbsolutePath());
    }

    /** 遞迴建立檔案、方法、端點與 SQL 索引。 */
    private void scan(Path root) throws IOException {
        try (Stream<Path> stream = Files.walk(root)) {
            stream.filter(Files::isRegularFile)
                    .filter(this::supported)
                    .filter(p -> !p.toString().contains("\\target\\") && !p.toString().contains("/target/"))
                    .forEach(this::indexFile);
        }
    }

    private void indexFile(Path path) {
        try {
            String text = Files.readString(path, StandardCharsets.UTF_8);
            String relative = path.toString();
            String fileNodeId = "FILE:" + relative;
            Node fileNode = new Node(fileNodeId, path, "檔案", relative, text);
            nodes.put(fileNodeId, fileNode);

            if (SQL.matcher(text).find() || path.toString().toLowerCase().endsWith(".sql")) {
                fileNode.sql = true;
            }
            if (path.toString().toLowerCase().endsWith(".java")) indexJava(path, text, fileNode);
            if (path.toString().toLowerCase().endsWith(".js")) indexJs(path, text, fileNode);
        } catch (Exception e) {
            warnings.add("無法讀取：" + path + "，原因：" + e.getMessage());
        }
    }

    private void indexJava(Path path, String text, Node fileNode) {
        String className = "未知類別";
        Matcher classMatcher = JAVA_CLASS.matcher(text);
        if (classMatcher.find()) className = classMatcher.group(1);
        Matcher matcher = JAVA_METHOD.matcher(text);
        while (matcher.find()) {
            String name = matcher.group(1);
            int end = matchingBrace(text, matcher.end() - 1);
            String body = text.substring(matcher.start(), end > 0 ? end : text.length());
            Node node = addMethod(path, className + "." + name, "Java 方法", body, line(text, matcher.start()));
            Matcher annotation = ANNOTATION_PATH.matcher(text.substring(Math.max(0, matcher.start() - 300), matcher.start()));
            while (annotation.find()) node.endpoint = annotation.group(2);
        }
        fileNode.label = className + "（檔案）";
    }

    private void indexJs(Path path, String text, Node fileNode) {
        Matcher matcher = JS_FUNCTION.matcher(text);
        while (matcher.find()) {
            String name = firstNonBlank(matcher.group(1), matcher.group(2), matcher.group(3));
            int end = matchingBrace(text, matcher.end() - 1);
            String body = text.substring(matcher.start(), end > 0 ? end : text.length());
            addMethod(path, name, "JavaScript 函式", body, line(text, matcher.start()));
        }
        fileNode.label = path.getFileName().toString() + "（JavaScript）";
    }

    private Node addMethod(Path path, String name, String type, String body, int line) {
        String id = "METHOD:" + path + ":" + name + ":" + line;
        Node node = new Node(id, path, type, name, body);
        node.line = line;
        node.sql = SQL.matcher(body).find();
        nodes.put(id, node);
        methodIndex.computeIfAbsent(name.substring(name.lastIndexOf('.') + 1), k -> new ArrayList<>()).add(node);
        return node;
    }

    /** 根據入口關鍵字建立可達呼叫鏈，並以 Markdown 輸出。 */
    private String buildReport(Path root, String entry) {
        List<Node> starts = nodes.values().stream()
                .filter(n -> n.label.toLowerCase().contains(entry.toLowerCase())
                        || n.path.toString().toLowerCase().contains(entry.toLowerCase())
                        || n.endpoint.toLowerCase().contains(entry.toLowerCase()))
                .sorted(Comparator.comparing(n -> n.path.toString()))
                .collect(Collectors.toList());
        StringBuilder out = new StringBuilder("# SQL 呼叫鏈掃描報告\n\n");
        out.append("- 專案：").append(root).append("\n- 入口：").append(entry).append("\n\n");
        if (starts.isEmpty()) out.append("> 找不到入口，請改用檔名、方法名或 URL 重新掃描。\n");
        for (Node start : starts) {
            out.append("## ").append(start.type).append("：").append(start.label).append("\n\n");
            appendChains(out, start);
        }
        if (!warnings.isEmpty()) {
            out.append("\n## 掃描警告\n\n");
            warnings.forEach(w -> out.append("- ").append(w).append("\n"));
        }
        return out.toString();
    }

    private void appendChains(StringBuilder out, Node start) {
        Deque<List<Node>> queue = new ArrayDeque<>();
        queue.add(List.of(start));
        Set<String> visited = new HashSet<>();
        int count = 0;
        while (!queue.isEmpty() && count++ < 100) {
            List<Node> chain = queue.removeFirst();
            Node current = chain.get(chain.size() - 1);
            if (current.sql || current.path.toString().toLowerCase().endsWith(".sql")) {
                out.append("### 呼叫鏈\n\n").append(formatChain(chain)).append("\n\n");
                continue;
            }
            for (Node next : nextNodes(current)) {
                if (chain.stream().anyMatch(n -> n.id.equals(next.id))) continue;
                String visitKey = current.id + "->" + next.id;
                if (visited.add(visitKey)) {
                    List<Node> extended = new ArrayList<>(chain);
                    extended.add(next);
                    queue.addLast(extended);
                }
            }
            if (nextNodes(current).isEmpty()) {
                out.append("### 未解析完成\n\n").append(formatChain(chain)).append(" → `未解析`\n\n");
            }
        }
    }

    private List<Node> nextNodes(Node current) {
        List<Node> result = new ArrayList<>();
        String body = current.content;
        for (Node candidate : nodes.values()) {
            if (candidate == current) continue;
            String shortName = candidate.label.substring(candidate.label.lastIndexOf('.') + 1);
            if (candidate.type.contains("方法") && body.matches("(?s).*\\b" + Pattern.quote(shortName) + "\\s*\\(.*")) {
                result.add(candidate);
            }
            if (candidate.type.equals("檔案") && body.toLowerCase().contains(candidate.path.getFileName().toString().toLowerCase())) {
                result.add(candidate);
            }
        }
        return result.stream().distinct().limit(20).collect(Collectors.toList());
    }

    private String formatChain(List<Node> chain) {
        return chain.stream().map(n -> n.type + " `" + n.label + "`（" + n.path.getFileName() + ":" + n.line + "）")
                .collect(Collectors.joining("\n  ↓\n"));
    }

    private boolean supported(Path p) {
        String name = p.getFileName().toString().toLowerCase();
        return EXTENSIONS.stream().anyMatch(name::endsWith);
    }

    private static int matchingBrace(String text, int open) {
        int depth = 0;
        for (int i = open; i < text.length(); i++) {
            if (text.charAt(i) == '{') depth++;
            if (text.charAt(i) == '}' && --depth == 0) return i + 1;
        }
        return -1;
    }

    private static int line(String text, int position) {
        return (int) text.substring(0, position).chars().filter(c -> c == '\n').count() + 1;
    }

    private static String firstNonBlank(String... values) {
        for (String value : values) if (value != null && !value.isBlank()) return value;
        return "匿名函式";
    }

    private static class Node {
        final String id;
        final Path path;
        final String type;
        String label;
        final String content;
        String endpoint = "";
        int line = 1;
        boolean sql;

        Node(String id, Path path, String type, String label, String content) {
            this.id = id; this.path = path; this.type = type; this.label = label; this.content = content;
        }
    }
}
