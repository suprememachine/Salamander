// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/**
 * @title BaseMineSwap
 * @dev Simple AMM DEX for SLAM/ETH pair (constant product x*y=k)
 *      Liquidity providers deposit SLAM + ETH, earn 0.3% swap fees
 */
contract BaseMineSwap {
    address public token;       // SLAM token address
    address public owner;

    uint256 public reserveETH;
    uint256 public reserveToken;
    uint256 public totalLiquidity;
    mapping(address => uint256) public liquidity;

    uint256 public constant FEE_NUMERATOR = 3;
    uint256 public constant FEE_DENOMINATOR = 1000; // 0.3% fee

    event Swap(address indexed user, bool isBuy, uint256 amountIn, uint256 amountOut);
    event LiquidityAdded(address indexed provider, uint256 ethAmount, uint256 tokenAmount, uint256 liquidityMinted);
    event LiquidityRemoved(address indexed provider, uint256 ethAmount, uint256 tokenAmount, uint256 liquidityBurned);

    modifier onlyOwner() {
        require(msg.sender == owner, "Not owner");
        _;
    }

    constructor(address _token) {
        token = _token;
        owner = msg.sender;
    }

    /**
     * @dev Add liquidity (ETH + SLAM). First deposit sets the price.
     *      Returns amount of LP tokens minted.
     */
    function addLiquidity() external payable {
        require(msg.value > 0, "Must send ETH");

        // Calculate token amount to deposit proportionally
        uint256 tokenAmount;
        if (totalLiquidity == 0) {
            // First deposit - caller must approve tokens first
            // msg.value is ETH, we need matching SLAM tokens
            // For initial pool: require msg.value worth of SLAM
            tokenAmount = msg.value * 1000; // Initial ratio: 1 ETH = 1000 SLAM
            require(tokenAmount > 0, "Invalid token amount");
        } else {
            // Proportional to existing reserves
            tokenAmount = (msg.value * reserveToken) / reserveETH;
        }

        // Transfer SLAM from caller
        bool sent = IERC20(token).transferFrom(msg.sender, address(this), tokenAmount);
        require(sent, "Token transfer failed");

        // Calculate LP tokens
        uint256 liquidityMinted;
        if (totalLiquidity == 0) {
            liquidityMinted = msg.value; // Initial LP = ETH amount
        } else {
            liquidityMinted = (msg.value * totalLiquidity) / reserveETH;
        }

        reserveETH += msg.value;
        reserveToken += tokenAmount;
        totalLiquidity += liquidityMinted;
        liquidity[msg.sender] += liquidityMinted;

        emit LiquidityAdded(msg.sender, msg.value, tokenAmount, liquidityMinted);
    }

    /**
     * @dev Remove liquidity. Burns LP tokens, returns ETH + SLAM.
     */
    function removeLiquidity(uint256 liquidityAmount) external {
        require(liquidityAmount > 0, "Amount must be > 0");
        require(liquidity[msg.sender] >= liquidityAmount, "Insufficient liquidity");

        uint256 ethAmount = (liquidityAmount * reserveETH) / totalLiquidity;
        uint256 tokenAmount = (liquidityAmount * reserveToken) / totalLiquidity;

        liquidity[msg.sender] -= liquidityAmount;
        totalLiquidity -= liquidityAmount;
        reserveETH -= ethAmount;
        reserveToken -= tokenAmount;

        // Transfer ETH and SLAM back
        (bool sent,) = payable(msg.sender).call{value: ethAmount}("");
        require(sent, "ETH transfer failed");
        IERC20(token).transfer(msg.sender, tokenAmount);

        emit LiquidityRemoved(msg.sender, ethAmount, tokenAmount, liquidityAmount);
    }

    /**
     * @dev Swap ETH for SLAM (BUY)
     */
    function swapETHForToken() external payable {
        require(msg.value > 0, "Must send ETH");
        require(reserveETH > 0 && reserveToken > 0, "No liquidity");

        uint256 amountInWithFee = msg.value * (FEE_DENOMINATOR - FEE_NUMERATOR);
        uint256 amountOut = (amountInWithFee * reserveToken) / (reserveETH * FEE_DENOMINATOR + amountInWithFee);
        require(amountOut > 0 && amountOut < reserveToken, "Insufficient output");

        // Update reserves BEFORE transfer
        reserveETH += msg.value;
        reserveToken -= amountOut;

        // Transfer SLAM to buyer
        IERC20(token).transfer(msg.sender, amountOut);

        emit Swap(msg.sender, true, msg.value, amountOut);
    }

    /**
     * @dev Swap SLAM for ETH (SELL)
     */
    function swapTokenForETH(uint256 tokenAmount) external {
        require(tokenAmount > 0, "Amount must be > 0");
        require(reserveETH > 0 && reserveToken > 0, "No liquidity");

        // Transfer SLAM to contract
        IERC20(token).transferFrom(msg.sender, address(this), tokenAmount);

        uint256 amountInWithFee = tokenAmount * (FEE_DENOMINATOR - FEE_NUMERATOR);
        uint256 amountOut = (amountInWithFee * reserveETH) / (reserveToken * FEE_DENOMINATOR + amountInWithFee);
        require(amountOut > 0 && amountOut < reserveETH, "Insufficient output");

        // Update reserves AFTER transfer
        reserveToken += tokenAmount;
        reserveETH -= amountOut;

        // Transfer ETH to seller
        (bool sent,) = payable(msg.sender).call{value: amountOut}("");
        require(sent, "ETH transfer failed");

        emit Swap(msg.sender, false, tokenAmount, amountOut);
    }

    /**
     * @dev Get expected output amount (BUY SLAM with ETH)
     */
    function getAmountOut(uint256 amountIn, bool isBuy) external view returns (uint256) {
        if (reserveETH == 0 || reserveToken == 0) return 0;

        uint256 amountInWithFee = amountIn * (FEE_DENOMINATOR - FEE_NUMERATOR);

        if (isBuy) {
            return (amountInWithFee * reserveToken) / (reserveETH * FEE_DENOMINATOR + amountInWithFee);
        } else {
            return (amountInWithFee * reserveETH) / (reserveToken * FEE_DENOMINATOR + amountInWithFee);
        }
    }

    /**
     * @dev Get current SLAM/ETH price
     */
    function getPrice() external view returns (uint256) {
        if (reserveETH == 0) return 0;
        return (reserveToken * 1e18) / reserveETH;
    }

    // Fallback to accept ETH
    receive() external payable {}
}

interface IERC20 {
    function transfer(address to, uint256 amount) external returns (bool);
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
    function approve(address spender, uint256 amount) external returns (bool);
}
